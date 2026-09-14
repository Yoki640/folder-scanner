use crate::scan::{hash_threads, HASH_SAMPLE_BYTES};
use std::collections::HashMap;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::SystemTime;

pub type HashCache = Mutex<HashMap<PathBuf, (u64, SystemTime, String)>>;

pub fn hash_file_sampled(path: &Path, size: u64, scratch: &mut Vec<u8>) -> Option<String> {
    let mut f = File::open(path).ok()?;
    let mut hasher = blake3::Hasher::new();
    let sample = HASH_SAMPLE_BYTES as usize;

    if scratch.len() < sample {
        scratch.resize(sample, 0);
    }

    if size <= 3 * HASH_SAMPLE_BYTES {
        loop {
            match f.read(&mut scratch[..sample]) {
                Ok(0) => break,
                Ok(n) => {
                    hasher.update(&scratch[..n]);
                }
                Err(_) => return None,
            }
        }
    } else {
        let mid = size / 2;
        let positions = [0u64, mid - HASH_SAMPLE_BYTES / 2, size - HASH_SAMPLE_BYTES];
        for pos in positions {
            if f.seek(SeekFrom::Start(pos)).is_err() {
                return None;
            }
            let mut read = 0usize;
            while read < sample {
                match f.read(&mut scratch[read..sample]) {
                    Ok(0) => break,
                    Ok(n) => read += n,
                    Err(_) => return None,
                }
            }
            hasher.update(&scratch[..read]);
        }
    }

    Some(hasher.finalize().to_hex().to_string())
}

pub fn cache_entry_valid(cache: &HashMap<PathBuf, (u64, SystemTime, String)>, path: &Path) -> Option<String> {
    if let Some((cached_size, cached_mtime, cached_hash)) = cache.get(path) {
        let md = std::fs::metadata(path).ok()?;
        if md.len() == *cached_size && md.modified().ok() == Some(*cached_mtime) {
            return Some(cached_hash.clone());
        }
    }
    None
}

pub fn hash_many_sampled(
    items: &[(PathBuf, u64)],
    cache: &HashCache,
    cancel: &Arc<AtomicBool>,
) -> HashMap<PathBuf, Option<String>> {
    let mut result: HashMap<PathBuf, Option<String>> = HashMap::new();
    let mut to_compute: Vec<(PathBuf, u64)> = Vec::new();

    {
        let cache_guard = cache.lock().unwrap();
        for (p, s) in items {
            if let Some(h) = cache_entry_valid(&cache_guard, p) {
                result.insert(p.clone(), Some(h));
            } else {
                to_compute.push((p.clone(), *s));
            }
        }
    }

    if to_compute.is_empty() {
        return result;
    }

    let threads = hash_threads().min(to_compute.len());
    let cursor = AtomicUsize::new(0);
    let out: Mutex<HashMap<PathBuf, Option<String>>> = Mutex::new(HashMap::new());
    let cache_arc: Arc<HashCache> = Arc::new(HashCache::new(HashMap::new()));

    std::thread::scope(|s| {
        for _ in 0..threads {
            s.spawn(|| {
                let mut scratch: Vec<u8> = Vec::new();
                loop {
                    if cancel.load(Ordering::SeqCst) {
                        break;
                    }
                    let idx = cursor.fetch_add(1, Ordering::SeqCst);
                    if idx >= to_compute.len() {
                        break;
                    }
                    let (p, size) = &to_compute[idx];
                    let h = hash_file_sampled(p, *size, &mut scratch);
                    if h.is_some() {
                        if let Ok(md) = std::fs::metadata(p) {
                            if let Some(mtime) = md.modified().ok() {
                                let mut cg = cache_arc.lock().unwrap();
                                cg.insert(p.clone(), (md.len(), mtime, h.clone().unwrap()));
                            }
                        }
                    }
                    out.lock().unwrap().insert(p.clone(), h);
                }
            });
        }
    });

    {
        let mut cache_guard = cache.lock().unwrap();
        for (k, v) in cache_arc.lock().unwrap().iter() {
            cache_guard.insert(k.clone(), v.clone());
        }
    }

    for (k, v) in out.into_inner().unwrap() {
        result.insert(k, v);
    }
    result
}