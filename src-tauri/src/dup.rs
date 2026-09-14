use crate::hash::{hash_many_sampled, HashCache};
use crate::scan::MIN_DUP_SIZE;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

/// Group candidate files by (basename, size), hash them, and return duplicate groups.
/// Each group is a list of (size, path) where all entries share basename+size+hash.
pub fn find_duplicates(
    candidates: &[(u64, String)],
    cache: &HashCache,
    cancel: &Arc<AtomicBool>,
) -> Vec<Vec<(u64, String)>> {
    if candidates.is_empty() {
        return Vec::new();
    }

    let mut by_key: HashMap<(String, u64), Vec<PathBuf>> = HashMap::new();
    for (size, path) in candidates {
        if *size < MIN_DUP_SIZE {
            continue;
        }
        let basename = Path::new(path)
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_default();
        by_key
            .entry((basename, *size))
            .or_default()
            .push(PathBuf::from(path));
    }

    let groups_only: Vec<((String, u64), Vec<PathBuf>)> = by_key
        .into_iter()
        .filter(|(_, v)| v.len() > 1)
        .collect();

    if groups_only.is_empty() || cancel.load(Ordering::SeqCst) {
        return Vec::new();
    }

    let mut tasks: Vec<(PathBuf, u64)> = Vec::new();
    for ((_, size), paths) in &groups_only {
        for p in paths {
            tasks.push((p.clone(), *size));
        }
    }

    let hashes = hash_many_sampled(&tasks, cache, cancel);

    if cancel.load(Ordering::SeqCst) {
        return Vec::new();
    }

    let mut final_map: HashMap<(String, u64, String), Vec<PathBuf>> = HashMap::new();
    for ((basename, size), paths) in &groups_only {
        for p in paths {
            if let Some(Some(h)) = hashes.get(p) {
                final_map
                    .entry((basename.clone(), *size, h.clone()))
                    .or_default()
                    .push(p.clone());
            }
        }
    }

    let mut groups: Vec<Vec<(u64, String)>> = Vec::new();
    for ((_, size, _), paths) in final_map {
        if paths.len() < 2 {
            continue;
        }
        let mut entries: Vec<(u64, String)> = paths
            .into_iter()
            .map(|p| (size, p.to_string_lossy().into_owned()))
            .collect();
        entries.sort_by(|a, b| a.1.cmp(&b.1));
        groups.push(entries);
    }

    groups.sort_by(|a, b| {
        let wa = a[0].0 * (a.len() as u64 - 1);
        let wb = b[0].0 * (b.len() as u64 - 1);
        wb.cmp(&wa)
    });

    groups
}