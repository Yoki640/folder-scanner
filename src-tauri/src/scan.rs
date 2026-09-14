use serde::Serialize;
use std::collections::{HashMap, VecDeque};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;

pub const MIN_DUP_SIZE: u64 = 1024 * 1024;
pub const HASH_SAMPLE_BYTES: u64 = 1024 * 1024;

const TOP_N: usize = 5;
const BUF_SIZE: usize = 1024 * 1024;
const DIR_BATCH: usize = 32;

#[derive(Serialize, Default, Clone)]
pub struct ScanResult {
    pub total_size: u64,
    pub total_files: u64,
    pub total_folders: u64,
    pub folder_sizes: HashMap<String, u64>,
    pub extension_sizes: HashMap<String, u64>,
    pub top_files: Vec<(u64, String)>,
    pub dup_candidates: Vec<(u64, String)>,
    pub system_skipped: bool,
    pub has_files: bool,
    pub disk_total: Option<u64>,
    pub disk_free: Option<u64>,
    pub fast_scan: bool,
    pub mode: String,
    pub root_path: String,
    pub elapsed_ms: u64,
}

/// Per-worker aggregation buffer; merged once at the end, so no global locks
/// are touched in the hot loop.
#[derive(Default)]
pub struct AggInner {
    pub total_size: u64,
    pub total_files: u64,
    pub total_folders: u64,
    pub extension_sizes: HashMap<String, u64>,
    pub top_files: Vec<(u64, String)>,
    pub dup_candidates: Vec<(u64, String)>,
    pub system_skipped: bool,
    pub has_files: bool,
}

impl AggInner {
    pub fn merge_into(&mut self, other: &AggInner) {
        self.total_size = self.total_size.saturating_add(other.total_size);
        self.total_files = self.total_files.saturating_add(other.total_files);
        self.total_folders = self.total_folders.saturating_add(other.total_folders);
        self.system_skipped = self.system_skipped || other.system_skipped;
        self.has_files = self.has_files || other.has_files;
        for (ext, sz) in &other.extension_sizes {
            *self.extension_sizes.entry(ext.clone()).or_insert(0) += sz;
        }
        for top in &other.top_files {
            top_push(&mut self.top_files, top.clone());
        }
        self.dup_candidates.extend(other.dup_candidates.iter().cloned());
    }
}

pub type ProgressFn = Box<dyn Fn(u8) + Send + Sync>;

/// Служебные файлы Windows (pagefile.sys, hiberfil.sys и т.п.) не показываются
/// и не считаются: они занимают место, но не читаются без прав администратора,
/// и их учёт искажает итоговые цифры (сумма становится больше ёмкости диска).
/// Папки по имени не пропускаются: читается всё доступное.
const SYSTEM_FILES: &[&str] = &[
    "pagefile.sys",
    "hiberfil.sys",
    "swapfile.sys",
    "DumpStack.log",
    "DumpStack.log.tmp",
];

#[inline]
fn is_system_file(name: &str) -> bool {
    SYSTEM_FILES.contains(&name)
}

/// Every system folder is scanned (Windows, System32, Program Files, ...).
/// Kept as a function so the MFT fast path behaves identically.
#[inline]
pub fn is_system_folder(_name: &str) -> bool {
    false
}

pub fn max_workers() -> usize {
    let cpus = std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(4);
    cpus.clamp(4, 16)
}

pub fn hash_threads() -> usize {
    let cpus = std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(4);
    (cpus / 2).clamp(1, 16)
}

#[inline]
fn ext_for(name: &str) -> String {
    Path::new(name)
        .extension()
        .map(|e| e.to_string_lossy().to_lowercase())
        .unwrap_or_default()
}

#[inline]
fn top_push(heap: &mut Vec<(u64, String)>, item: (u64, String)) {
    if heap.len() < TOP_N || item.0 > heap[0].0 {
        heap.push(item);
        heap.sort();
        if heap.len() > TOP_N {
            heap.drain(..heap.len() - TOP_N);
        }
    }
}

#[inline]
pub(crate) fn add_file(parent: &Path, name: &str, size: u64, agg: &mut AggInner) {
    if size == 0 || is_system_file(name) {
        return;
    }
    agg.total_files += 1;
    agg.total_size = agg.total_size.saturating_add(size);
    agg.has_files = true;

    let ext = ext_for(name);
    *agg.extension_sizes.entry(ext).or_insert(0) += size;

    // Build the full path lazily: only for the top-N books and for >= 1MB
    // duplicate candidates. parent + name so the stored path always points
    // at the file, never at its parent folder.
    let need_top = agg.top_files.len() < TOP_N
        || agg.top_files.first().map(|t| size > t.0).unwrap_or(false);
    if need_top || size >= MIN_DUP_SIZE {
        let p = parent.join(name).to_string_lossy().into_owned();
        if need_top {
            top_push(&mut agg.top_files, (size, p.clone()));
        }
        if size >= MIN_DUP_SIZE {
            agg.dup_candidates.push((size, p));
        }
    }
}

#[derive(Debug)]
pub struct DirEntry {
    pub name: String,
    pub size: u64,
    pub is_directory: bool,
    pub is_reparse: bool,
}

#[cfg(windows)]
mod nt {
    use super::DirEntry;

    pub(super) type NtStatus = i32;
    pub(super) type WinHandle = isize;
    pub(super) const INVALID_HANDLE_VALUE: WinHandle = -1;
    pub(super) const STATUS_SUCCESS: NtStatus = 0;
    pub(super) const STATUS_NO_MORE_FILES: NtStatus = -2147483642;
    pub(super) const FILE_DIRECTORY_INFORMATION_CLASS: u32 = 1;
    pub(super) const FILE_LIST_DIRECTORY: u32 = 0x00000001;
    pub(super) const FILE_SHARE_READ: u32 = 0x00000001;
    pub(super) const FILE_SHARE_WRITE: u32 = 0x00000002;
    pub(super) const FILE_SHARE_DELETE: u32 = 0x00000004;
    pub(super) const OPEN_EXISTING: u32 = 3;
    pub(super) const FILE_FLAG_BACKUP_SEMANTICS: u32 = 0x02000000;
    pub(super) const FILE_ATTRIBUTE_DIRECTORY: u32 = 0x10;
    pub(super) const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x400;
    // FILE_DIRECTORY_INFORMATION fixed part; FileName starts at offset 64.
    pub(super) const HDR: usize = 64;

    #[repr(C)]
    pub(super) struct IoStatusBlock {
        pub(super) status: NtStatus,
        pub(super) information: usize,
    }

    #[repr(C)]
    #[allow(dead_code)]
    pub(super) struct FileDirectoryInformation {
        pub(super) next_entry_offset: u32,
        pub(super) file_index: u32,
        pub(super) creation_time: i64,
        pub(super) last_access_time: i64,
        pub(super) last_write_time: i64,
        pub(super) change_time: i64,
        pub(super) end_of_file: i64,
        pub(super) allocation_size: i64,
        pub(super) file_attributes: u32,
        pub(super) file_name_length: u32,
    }

    #[link(name = "kernel32")]
    extern "system" {
        pub(super) fn CreateFileW(
            lpfilename: *const u16,
            dwdesiredaccess: u32,
            dwsharemode: u32,
            lpsecurityattributes: *const core::ffi::c_void,
            dwcreationdisposition: u32,
            dwflagsandattributes: u32,
            htemplatefile: WinHandle,
        ) -> WinHandle;
        pub(super) fn CloseHandle(hobject: WinHandle) -> i32;
    }

    #[link(name = "ntdll")]
    extern "system" {
        pub(super) fn NtQueryDirectoryFile(
            file_handle: WinHandle,
            event: WinHandle,
            apc_routine: *mut core::ffi::c_void,
            apc_context: *mut core::ffi::c_void,
            io_status_block: *mut IoStatusBlock,
            buffer: *mut core::ffi::c_void,
            length: u32,
            file_information_class: u32,
            return_single_entry: u8,
            file_name: *mut core::ffi::c_void,
            restart_scan: u8,
        ) -> NtStatus;
    }

    /// Push one record from the current chunk at `offset` into `out`, decoding
    /// the name only if it survives the cheap attribute pre-filter. Returns the
    /// next record offset (0 stops the chunk loop).
    #[inline]
    pub(super) fn push_entry(
        buffer: &[u8],
        offset: usize,
        info: &FileDirectoryInformation,
        out: &mut Vec<DirEntry>,
        name_buf: &mut String,
    ) -> usize {
        let attrs = info.file_attributes;
        let next = info.next_entry_offset as usize;
        let is_dir = attrs & FILE_ATTRIBUTE_DIRECTORY != 0;
        let size = info.end_of_file as u64;

        if attrs & FILE_ATTRIBUTE_REPARSE_POINT != 0 {
            return next;
        }
        if !is_dir && size == 0 {
            return next;
        }

        let name_len = info.file_name_length as usize;
        let name_chars = name_len / 2;
        // Skip "." and ".." before decoding anything.
        if name_chars >= 1 && name_chars <= 2 {
            let start = offset + HDR;
            let first = buffer[start] as u16 | ((buffer[start + 1] as u16) << 8);
            if first == b'.' as u16
                && (name_chars == 1 || buffer[start + 2] as u16 == b'.' as u16)
            {
                return next;
            }
        }

        let name_units: &[u16] = unsafe {
            std::slice::from_raw_parts(
                buffer.as_ptr().add(offset + HDR) as *const u16,
                name_chars,
            )
        };
        name_buf.clear();
        // ASCII fast path: most NTFS names are ASCII, so decode a single byte
        // per char without the full UTF-16 machinery per char.
        if name_units.iter().all(|&u| u <= 0x7F) {
            name_buf.reserve(name_chars);
            for &u in name_units {
                name_buf.push(u as u8 as char);
            }
        } else {
            name_buf.extend(char::decode_utf16(name_units.iter().copied()).map(|r| r.unwrap_or('\u{FFFD}')));
        }

        out.push(DirEntry {
            name: name_buf.clone(),
            size,
            is_directory: is_dir,
            is_reparse: false,
        });
        next
    }
}

/// Read a directory and return name + size + is_dir WITHOUT any extra stat:
/// on Windows a single NtQueryDirectoryFile (FILE_DIRECTORY_INFORMATION) already
/// carries file size and attributes, so sizes are free.
///
/// `wide` is a scratch buffer reused across calls so we never re-encode the
/// directory path (one allocation per directory, not per file). Zero-size and
/// reparse entries are dropped BEFORE their names are decoded into a `String`,
/// so the common case (huge trees full of small files) allocates very little.
#[cfg(windows)]
fn enum_dir(
    dir: &Path,
    wide: &mut Vec<u16>,
    buffer: &mut Vec<u8>,
    out: &mut Vec<DirEntry>,
) -> std::io::Result<()> {
    use std::os::windows::ffi::OsStrExt;

    use crate::scan::nt::*;

    wide.clear();
    wide.extend(dir.as_os_str().encode_wide());
    wide.push(0);

    let handle = unsafe {
        CreateFileW(
            wide.as_ptr(),
            FILE_LIST_DIRECTORY,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            std::ptr::null(),
            OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS,
            0,
        )
    };
    if handle == INVALID_HANDLE_VALUE {
        return Err(std::io::Error::last_os_error());
    }

    if buffer.len() < BUF_SIZE {
        buffer.resize(BUF_SIZE, 0);
    }
    out.clear();

    let mut name_buf: String = String::new();

    loop {
        let mut iosb = IoStatusBlock {
            status: 0,
            information: 0,
        };
        let status = unsafe {
            NtQueryDirectoryFile(
                handle,
                0,
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                &mut iosb,
                buffer.as_mut_ptr() as *mut core::ffi::c_void,
                BUF_SIZE as u32,
                FILE_DIRECTORY_INFORMATION_CLASS,
                0,
                std::ptr::null_mut(),
                0,
            )
        };
        if status == STATUS_NO_MORE_FILES {
            break;
        }
        if status != STATUS_SUCCESS {
            unsafe {
                CloseHandle(handle);
            }
            return Err(std::io::Error::from_raw_os_error(status));
        }

        let nbytes = iosb.information;
        if nbytes == 0 {
            break;
        }
        let mut offset = 0usize;
        while offset + HDR <= nbytes {
            let info = unsafe { &*(buffer.as_ptr().add(offset) as *const FileDirectoryInformation) };
            let next = push_entry(buffer, offset, info, out, &mut name_buf);
            if next == 0 {
                break;
            }
            offset += next;
        }
    }

    unsafe {
        CloseHandle(handle);
    }
    Ok(())
}

#[cfg(target_os = "macos")]
fn enum_dir(
    dir: &Path,
    _wide: &mut Vec<u16>,
    buffer: &mut Vec<u8>,
    out: &mut Vec<DirEntry>,
) -> std::io::Result<()> {
    use std::os::unix::io::AsRawFd;

    const ATTR_BIT_MAP_COUNT: u16 = 5;
    const ATTR_CMN_RETURNED_ATTRS: u32 = 0x80000000;
    const ATTR_CMN_NAME: u32 = 0x00000001;
    const ATTR_CMN_OBJTYPE: u32 = 0x00000008;
    const ATTR_FILE_TOTALSIZE: u32 = 0x00000002;
    const VDIR: u32 = 2;
    const VLNK: u32 = 5;

    #[repr(C)]
    struct AttrList {
        bitmapcount: u16,
        reserved: u16,
        commonattr: u32,
        volattr: u32,
        dirattr: u32,
        fileattr: u32,
        forkattr: u32,
    }

    extern "C" {
        fn getattrlistbulk(
            dirfd: i32,
            alist: *const AttrList,
            attrBuf: *mut u8,
            attrBufSize: usize,
            options: u64,
        ) -> i32;
    }

    out.clear();

    let file = std::fs::File::open(dir)?;
    let fd = file.as_raw_fd();

    let attr_list = AttrList {
        bitmapcount: ATTR_BIT_MAP_COUNT,
        reserved: 0,
        commonattr: ATTR_CMN_RETURNED_ATTRS | ATTR_CMN_NAME | ATTR_CMN_OBJTYPE,
        volattr: 0,
        dirattr: 0,
        fileattr: ATTR_FILE_TOTALSIZE,
        forkattr: 0,
    };

    const BULK_BUF: usize = 1024 * 1024;
    if buffer.len() < BULK_BUF {
        buffer.resize(BULK_BUF, 0);
    }

    loop {
        let ret = unsafe {
            getattrlistbulk(fd, &attr_list, buffer.as_mut_ptr(), BULK_BUF, 0)
        };
        if ret <= 0 {
            break;
        }
        let entry_count = ret as usize;
        let mut pos = 0usize;

        'entries: for _ in 0..entry_count {
            if pos + 4 > buffer.len() {
                break 'entries;
            }
            let entry_len =
                u32::from_ne_bytes(buffer[pos..pos + 4].try_into().unwrap()) as usize;
            if entry_len < 24 || pos + entry_len > buffer.len() {
                break 'entries;
            }
            let entry_end = pos + entry_len;
            pos += 4;

            // attribute_set_t — 5 × u32 = 20 bytes
            if pos + 20 > entry_end {
                break 'entries;
            }
            let returned_common =
                u32::from_ne_bytes(buffer[pos..pos + 4].try_into().unwrap());
            let returned_file =
                u32::from_ne_bytes(buffer[pos + 12..pos + 16].try_into().unwrap());
            pos += 20;

            let mut name: Option<String> = None;
            let mut obj_type: u32 = 0;
            let mut size: u64 = 0;

            // NAME (attrreference: i32 offset + u32 length)
            if returned_common & ATTR_CMN_NAME != 0 {
                if pos + 8 > entry_end {
                    break 'entries;
                }
                let data_offset = i32::from_ne_bytes(
                    buffer[pos..pos + 4].try_into().unwrap(),
                ) as isize;
                let data_len = u32::from_ne_bytes(
                    buffer[pos + 4..pos + 8].try_into().unwrap(),
                ) as usize;
                let name_ptr = pos as isize + data_offset;
                pos += 8;

                if name_ptr >= 0
                    && (name_ptr as usize) + data_len <= entry_end
                    && data_len > 1
                {
                    let nb = &buffer[name_ptr as usize..name_ptr as usize + data_len - 1];
                    name = std::str::from_utf8(nb)
                        .ok()
                        .map(|s| s.to_owned());
                }
            }

            // OBJTYPE (u32)
            if returned_common & ATTR_CMN_OBJTYPE != 0 {
                if pos + 4 > entry_end {
                    break 'entries;
                }
                obj_type =
                    u32::from_ne_bytes(buffer[pos..pos + 4].try_into().unwrap());
                pos += 4;
            }

            // TOTALSIZE (i64) — present only for non-directory entries
            if returned_file & ATTR_FILE_TOTALSIZE != 0 {
                if pos + 8 > entry_end {
                    break 'entries;
                }
                size = u64::from_ne_bytes(
                    buffer[pos..pos + 8].try_into().unwrap(),
                );
                pos += 8;
            }

            // Advance past any remaining attrs we didn't parse
            pos = entry_end;

            let name = match name {
                Some(n) if !n.is_empty() && n != "." && n != ".." => n,
                _ => continue,
            };

            out.push(DirEntry {
                name,
                size,
                is_directory: obj_type == VDIR,
                is_reparse: obj_type == VLNK,
            });
        }
    }

    Ok(())
}

#[cfg(not(any(windows, target_os = "macos")))]
fn enum_dir(
    dir: &Path,
    _wide: &mut Vec<u16>,
    _buffer: &mut Vec<u8>,
    out: &mut Vec<DirEntry>,
) -> std::io::Result<()> {
    out.clear();
    for entry in std::fs::read_dir(dir)? {
        let entry = entry?;
        let name = entry.file_name().to_string_lossy().into_owned();
        let ftype = entry.file_type().ok();
        let size = if ftype.as_ref().is_some_and(|t| t.is_dir()) {
            0
        } else {
            entry.metadata().map(|m| m.len()).unwrap_or(0)
        };
        let is_symlink = ftype.as_ref().is_some_and(|t| t.is_symlink());
        out.push(DirEntry {
            name,
            size,
            is_directory: ftype.as_ref().is_some_and(|t| t.is_dir()),
            is_reparse: is_symlink,
        });
    }
    Ok(())
}

pub fn scan_root(
    root: &Path,
    cancel: &Arc<AtomicBool>,
    progress: ProgressFn,
) -> Result<ScanResult, String> {
    let root_name = root.to_string_lossy().into_owned();

    struct Shared {
        queue: Mutex<VecDeque<PathBuf>>,
        remaining: AtomicU64, // queued + in-flight
        visited: AtomicU64,
        last_pct: AtomicU64,
    }
    let shared = Shared {
        queue: Mutex::new(VecDeque::new()),
        remaining: AtomicU64::new(0),
        visited: AtomicU64::new(0),
        last_pct: AtomicU64::new(0),
    };
    shared.queue.lock().unwrap().push_back(root.to_path_buf());
    shared.remaining.store(1, Ordering::Release);

    let workers = max_workers();
    let results: Mutex<Vec<(AggInner, HashMap<String, u64>, bool)>> =
        Mutex::new(Vec::with_capacity(workers));

    thread::scope(|s| {
        for _ in 0..workers {
            s.spawn(|| {
                let mut local_agg = AggInner::default();
                let mut local_fs: HashMap<String, u64> = HashMap::new();
                let mut local_sys = false;
                let mut buffer: Vec<u8> = Vec::new();
                let mut wide: Vec<u16> = Vec::new();
                let mut entries: Vec<DirEntry> = Vec::with_capacity(256);

                loop {
                    // Pull a batch of directories under a single lock
                    // acquisition instead of one directory at a time.
                    let dirs = {
                        let mut q = shared.queue.lock().unwrap();
                        let take = q.len().min(DIR_BATCH);
                        let mut out: Vec<PathBuf> = Vec::with_capacity(take);
                        for _ in 0..take {
                            if let Some(d) = q.pop_front() {
                                out.push(d);
                            }
                        }
                        out
                    };

                    if dirs.is_empty() {
                        if shared.remaining.load(Ordering::Acquire) == 0 {
                            break;
                        }
                        thread::yield_now();
                        continue;
                    }

                    for dir in dirs {
                        // Note: `remaining` still counts this directory until
                        // processing is done, so sibling workers can't exit
                        // early while a folder is mid-flight (children may
                        // still be pushed). We decrement once, at the very end.
                        if cancel.load(Ordering::Relaxed) {
                            shared.remaining.store(0, Ordering::Release);
                            break;
                        }

                        if enum_dir(&dir, &mut wide, &mut buffer, &mut entries).is_err() {
                            local_sys = true; // most commonly Access Denied
                            shared.remaining.fetch_sub(1, Ordering::Release);
                            continue;
                        }

                        let visited = shared.visited.fetch_add(1, Ordering::Relaxed) + 1;
                        let mut bucket_size: u64 = 0;
                        let mut child_dirs: Vec<PathBuf> = Vec::new();

                        for e in &entries {
                            // Reparse points (junctions / symlinks) resolve to real
                            // content already counted at its physical location, so
                            // they must NOT be expanded or sized again.
                            if e.is_reparse {
                                continue;
                            }
                            if e.is_directory {
                                // Never skip by name: read everything reachable.
                                local_agg.total_folders += 1;
                                child_dirs.push(dir.join(&e.name));
                            } else if e.size > 0 {
                                bucket_size = bucket_size.saturating_add(e.size);
                                add_file(&dir, &e.name, e.size, &mut local_agg);
                            }
                        }

                        // Push all children at once: a single lock + one
                        // counter bump per batch instead of per folder.
                        if !child_dirs.is_empty() {
                            let n = child_dirs.len() as u64;
                            {
                                let mut q = shared.queue.lock().unwrap();
                                q.extend(child_dirs.drain(..));
                            }
                            shared.remaining.fetch_add(n, Ordering::Release);
                        }

                        if bucket_size > 0 {
                            let bucket = dir
                                .strip_prefix(root)
                                .ok()
                                .and_then(|r| r.components().next())
                                .map(|c| c.as_os_str().to_string_lossy().into_owned())
                                .unwrap_or_else(|| "(в корне)".to_string());
                            *local_fs.entry(bucket).or_insert(0) += bucket_size;
                        }

                        // Monotonic progress: pct = finished / launched,
                        // throttled to avoid flooding the UI.
                        if visited % 32 == 0 {
                            let queued = shared.remaining.load(Ordering::Acquire);
                            let pct = ((visited.saturating_mul(99)
                                / (visited + queued).max(1)) as u8)
                                .min(99);
                            let prev = shared.last_pct.load(Ordering::Relaxed) as u8;
                            if pct > prev {
                                shared.last_pct.store(pct as u64, Ordering::Relaxed);
                                (progress)(pct);
                            }
                        }

                        shared.remaining.fetch_sub(1, Ordering::Release);
                    }
                }

                results.lock().unwrap().push((local_agg, local_fs, local_sys));
            });
        }
    });

    (progress)(100);

    let parts = results.into_inner().unwrap();
    let mut agg = AggInner::default();
    let mut folder_sizes: HashMap<String, u64> = HashMap::new();
    let mut sys = false;

    for (a, fs, s) in parts {
        agg.merge_into(&a);
        for (k, v) in fs {
            *folder_sizes.entry(k).or_insert(0) += v;
        }
        sys = sys || s;
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

    Ok(ScanResult {
        total_size: agg.total_size,
        total_files: agg.total_files,
        total_folders: agg.total_folders,
        folder_sizes,
        extension_sizes: agg.extension_sizes,
        top_files: top,
        dup_candidates: agg.dup_candidates,
        system_skipped: sys,
        has_files: agg.has_files,
        disk_total,
        disk_free,
        fast_scan: false,
        mode: "walk".to_string(),
        root_path: root_name,
        elapsed_ms: 0,
    })
}

#[cfg(test)]
mod bench {
    use super::*;
    use std::time::Instant;

    #[test]
    #[ignore]
    fn bench_scan_release() {
        let path = std::env::var("BENCH_PATH").expect("set BENCH_PATH");
        let root = PathBuf::from(path);
        let cancel = Arc::new(AtomicBool::new(false));
        let start = Instant::now();
        match scan_root(&root, &cancel, Box::new(|_| {})) {
            Ok(r) => {
                let secs = start.elapsed().as_secs_f64();
                println!(
                    "BENCH main: files={} dirs={} size={} time={:.2}s rate={:.0} files/s",
                    r.total_files,
                    r.total_folders,
                    r.total_size,
                    secs,
                    r.total_files as f64 / secs
                );
            }
            Err(e) => eprintln!("BENCH main: ERROR: {}", e),
        }
    }
}