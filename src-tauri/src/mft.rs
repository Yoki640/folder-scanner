use crate::scan::{add_file, is_system_folder, max_workers, AggInner, ProgressFn, ScanResult};
use ntfs_reader::api::{NtfsAttributeType, FIRST_NORMAL_RECORD, ROOT_RECORD};
use ntfs_reader::file::NtfsFile;
use ntfs_reader::mft::Mft;
use ntfs_reader::volume::Volume;
use std::collections::{HashMap, HashSet};
use std::fs;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{SystemTime, UNIX_EPOCH};

/// One live MFT record normalized to what the aggregator needs.
struct Node {
    parent: u64,
    name: String,
    size: u64,
    is_dir: bool,
}

/// Scan the volume that contains `root` using the NTFS MFT directly.
///
/// Returns `Some(ScanResult)` on success. Returns `None` (so the caller
/// falls back to the classic recursive walk) whenever the fast path does not
/// apply: not a Windows drive path, non-NTFS volume, not elevated, MFT read
/// failure, or the selected folder does not resolve inside the MFT.
pub fn scan_mft(root: &Path, cancel: &Arc<AtomicBool>, progress: ProgressFn) -> Option<ScanResult> {
    let (drive, comps) = drive_and_components(root)?;
    let device = PathBuf::from(format!("\\\\.\\{}:", drive));

    if !is_ntfs_volume(&device) {
        return None;
    }

    let volume = match Volume::new(&device) {
        Ok(v) => v,
        Err(_) => return None,
    };
    let mft = match Mft::new(volume) {
        Ok(m) => m,
        Err(_) => return None,
    };
    let max = mft.max_record;

    // Pass 1: extract one normalized node per live file record.
    // The whole $MFT table is resident in memory inside `mft` and every
    // accessor (record_exists / get_record / get_best_file_name / file_size)
    // is a read-only `&self` call, so the record range can be decoded by
    // several workers at once without any locks or clones.
    let mut nodes: Vec<Option<Node>> = (0..max as usize).map(|_| None).collect();
    let done: AtomicU64 = AtomicU64::new(0);
    let last_pct: AtomicU64 = AtomicU64::new(0);
    let last_emit_ms: AtomicU64 = AtomicU64::new(0);
    let workers = max_workers();
    let span = max - FIRST_NORMAL_RECORD;
    let chunk = span.div_ceil(workers as u64).max(1);

    let collected: Vec<Vec<(u64, Node)>> = thread::scope(|s| {
        let mut handles = Vec::with_capacity(workers);
        let mft_ref = &mft;
        let pct_ref = &last_pct;
        let emit_ref = &last_emit_ms;
        let prog_ref = &progress;
        let cancel_ref = cancel;
        let done_ref = &done;
        for t in 0..workers {
            let start = FIRST_NORMAL_RECORD + (t as u64) * chunk;
            let end = (start + chunk).min(max);
            if start >= end {
                continue;
            }
            handles.push(s.spawn(move || {
                let mut local: Vec<(u64, Node)> = Vec::new();
                for n in start..end {
                    if cancel_ref.load(Ordering::Relaxed) {
                        break;
                    }
                    if !mft_ref.record_exists(n) {
                        continue;
                    }
                    let rec = match mft_ref.get_record(n) {
                        Some(r) => r,
                        None => continue,
                    };
                    if !rec.is_used() || rec.is_extension() {
                        continue;
                    }
                    let name_attr = match rec.get_best_file_name(mft_ref) {
                        Some(na) => na,
                        None => continue,
                    };
                    local.push((
                        n,
                        Node {
                            parent: name_attr.parent(),
                            name: name_attr.to_string(),
                            size: file_size(mft_ref, &rec),
                            is_dir: rec.is_directory(),
                        },
                    ));
                }
                let processed = done_ref.fetch_add(local.len() as u64, Ordering::Relaxed)
                    + local.len() as u64;
                emit_progress_par(
                    pct_ref,
                    emit_ref,
                    1,
                    72,
                    processed,
                    span,
                    prog_ref,
                );
                local
            }));
        }
        handles.into_iter().map(|h| h.join().unwrap_or_default()).collect()
    });

    for part in collected {
        for (n, node) in part {
            nodes[n as usize] = Some(node);
        }
    }

    // Pass 2: parent -> children index (sorted by parent) for the whole volume.
    let mut pairs: Vec<(u64, u64)> = Vec::with_capacity(nodes.len());
    for (n, m) in nodes.iter().enumerate() {
        if let Some(m) = m {
            pairs.push((m.parent, n as u64));
        }
    }
    pairs.sort_unstable();

    let children_of = |rec: u64| -> &[(u64, u64)] {
        let lo = pairs.partition_point(|&(p, _)| p < rec);
        let hi = pairs.partition_point(|&(p, _)| p <= rec);
        &pairs[lo..hi]
    };

    // Pass 3: resolve the selected folder to its MFT record by walking the
    // name chain from the volume root (record 5).
    let mut cur = ROOT_RECORD;
    for comp in &comps {
        let mut next = None;
        for &(_, child) in children_of(cur) {
            let Some(m) = &nodes[child as usize] else { continue };
            if m.is_dir && m.name.to_lowercase() == *comp {
                next = Some(child);
                break;
            }
        }
        cur = next?;
    }
    let root_rec = cur;

    // Pass 3.5: quick memory-only count of reachable nodes in the selected
    // subtree (estimate of the work ahead) so pass 4 can report progress.
    let mut subtree_nodes = 0u64;
    {
        let mut svis: HashSet<u64> = HashSet::new();
        let mut sstack: Vec<u64> = vec![root_rec];
        while let Some(rec) = sstack.pop() {
            if !svis.insert(rec) {
                continue;
            }
            for &(_, child) in children_of(rec) {
                if child == rec {
                    continue;
                }
                if let Some(m) = &nodes[child as usize] {
                    if m.is_dir {
                        sstack.push(child);
                    }
                    subtree_nodes += 1;
                }
            }
        }
    }
    emit_progress_par(&last_pct, &last_emit_ms, 72, 73, 1, 1, &progress);

    // Pass 4: depth-first walk over the selected subtree, aggregating exactly
    // like scan_root does (buckets by first path component, system folders
    // skipped anywhere, files accumulated via add_file).
    let root_display = root.to_string_lossy().into_owned();
    let mut agg = AggInner::default();
    let mut folder_sizes: HashMap<String, u64> = HashMap::new();
    let mut visited: HashSet<u64> = HashSet::new();

    // (record, absolute display path, bucket or None at root, is_root)
    let mut stack: Vec<(u64, String, Option<String>, bool)> =
        vec![(root_rec, root_display.clone(), None, true)];
    let mut done = 0u64;

    while let Some((rec, path, bucket, is_root)) = stack.pop() {
        if cancel.load(Ordering::SeqCst) {
            break;
        }
        if !is_root && !visited.insert(rec) {
            continue;
        }
        for &(_, child) in children_of(rec) {
            if cancel.load(Ordering::SeqCst) {
                break;
            }
            if child == rec {
                continue;
            }
            let Some(m) = &nodes[child as usize] else { continue };
            if m.is_dir {
                if is_system_folder(&m.name) {
                    agg.system_skipped = true;
                    continue;
                }
                agg.total_folders += 1;
                let child_path = join_path(&path, &m.name);
                let child_bucket = match &bucket {
                    Some(b) => Some(b.clone()),
                    None => Some(m.name.clone()),
                };
                stack.push((child, child_path, child_bucket, false));
            } else {
                if m.size > 0 {
                    match &bucket {
                        Some(b) => {
                            *folder_sizes.entry(b.clone()).or_insert(0) += m.size;
                        }
                        None => {
                            *folder_sizes.entry("(в корне)".to_string()).or_insert(0) += m.size;
                        }
                    }
                }
                add_file(Path::new(&path), &m.name, m.size, &mut agg);
            }
            done += 1;
        }
        emit_progress_par(&last_pct, &last_emit_ms, 74, 99, done, subtree_nodes, &progress);
    }

    let mut top = agg.top_files;
    top.reverse();

    let (disk_total, disk_free) = if super::disk::is_drive_root(root) {
        super::disk::disk_usage(root)
            .map(|(t, f)| (Some(t), Some(f)))
            .unwrap_or((None, None))
    } else {
        (None, None)
    };

    Some(ScanResult {
        total_size: agg.total_size,
        total_files: agg.total_files,
        total_folders: agg.total_folders,
        folder_sizes,
        extension_sizes: agg.extension_sizes,
        top_files: top,
        dup_candidates: agg.dup_candidates,
        system_skipped: agg.system_skipped,
        has_files: agg.has_files,
        disk_total,
        disk_free,
        fast_scan: true,
        mode: "mft".to_string(),
        root_path: root_display,
        elapsed_ms: 0,
    })
}

/// Extract the logical size of a file from its unnamed `$DATA` attribute,
/// merging base and extension records (same rule as the crate's FileInfo).
fn file_size(mft: &Mft, rec: &NtfsFile<'_>) -> u64 {
    let mut size = 0u64;
    for record in mft.file_records(rec) {
        record.attributes(|att| {
            if att.header.type_id == NtfsAttributeType::Data as u32
                && att.header.name_length == 0
            {
                if let Some(h) = att.nonresident_header() {
                    if h.lowest_vcn == 0 {
                        size = h.data_size;
                    }
                } else if let Some(h) = att.resident_header() {
                    size = h.value_length as u64;
                }
            }
        });
    }
    size
}

/// Split `root` into (drive letter, lowercase relative components). Returns
/// `None` for UNC paths, relative paths and everything that is not a hard
/// `C:\...` style path.
fn drive_and_components(root: &Path) -> Option<(char, Vec<String>)> {
    let mut comps = Vec::new();
    for c in root.components() {
        match c {
            Component::Prefix(p) => match p.kind() {
                std::path::Prefix::Disk(d) => return Some((d as u8 as char, comps)),
                _ => return None,
            },
            Component::RootDir => {}
            Component::Normal(os) => comps.push(os.to_string_lossy().to_lowercase()),
            _ => return None,
        }
    }
    None
}

/// Cheap check that the volume is NTFS by reading the boot sector OEM id.
fn is_ntfs_volume(device: &Path) -> bool {
    let mut f = match fs::File::open(device) {
        Ok(f) => f,
        Err(_) => return false,
    };
    if f.seek(SeekFrom::Start(3)).is_err() {
        return false;
    }
    let mut blob = [0u8; 8];
    if f.read(&mut blob).unwrap_or(0) < 8 {
        return false;
    }
    &blob == b"NTFS    "
}

fn join_path(base: &str, name: &str) -> String {
    if base.ends_with('\\') || base.ends_with('/') {
        format!("{base}{name}")
    } else {
        format!("{base}\\{name}")
    }
}

/// Monotonic, throttled progress for the MFT flow. `last_pct` / `last_emit_ms`
/// are atomics so Pass 1 can report from several worker threads at once
/// without locks and without backwards jumps (+3% per 25ms max). Scaled into
/// the `from..=to` band so each stage maps to a sensible range.
fn emit_progress_par(
    last_pct: &AtomicU64,
    last_emit_ms: &AtomicU64,
    from: u8,
    to: u8,
    processed: u64,
    total: u64,
    cb: &ProgressFn,
) {
    if total == 0 || to <= from {
        return;
    }
    let frac = processed.min(total) as f64 / total as f64;
    let raw = (from as f64 + (to as f64 - from as f64) * frac) as u8;
    let raw = raw.clamp(1, 99);
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0);
    if now.saturating_sub(last_emit_ms.load(Ordering::Relaxed)) < 25 {
        return;
    }
    let prev = last_pct.load(Ordering::Relaxed) as u8;
    let target = raw.min(prev.saturating_add(3));
    if target <= prev {
        return;
    }
    last_pct.store(target as u64, Ordering::Relaxed);
    last_emit_ms.store(now, Ordering::Relaxed);
    cb(target);
}

#[cfg(test)]
mod bench {
    use super::*;
    use std::time::Instant;

    #[test]
    #[ignore]
    fn bench_mft() {
        let path = std::env::var("BENCH_MFT").expect("set BENCH_MFT");
        let root = PathBuf::from(&path);
        if !root.is_dir() {
            eprintln!("BENCH MFT: path is not a directory: {path}");
            return;
        }
        let cancel = Arc::new(AtomicBool::new(false));
        let start = Instant::now();
        match scan_mft(&root, &cancel, Box::new(|_| {})) {
            Some(r) => {
                let secs = start.elapsed().as_secs_f64();
                println!(
                    "BENCH MFT: files={} dirs={} size={} time={:.2}s rate={:.0} files/s",
                    r.total_files,
                    r.total_folders,
                    r.total_size,
                    secs,
                    r.total_files as f64 / secs
                );
            }
            None => eprintln!("BENCH MFT: fast path not applicable (elevate + NTFS volume)"),
        }
    }
}