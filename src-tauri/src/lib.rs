mod disk;
mod dup;
mod hash;
#[cfg(target_os = "windows")]
mod mft;
mod reveal;
mod scan;

use hash::HashCache;
use scan::ScanResult;
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use tauri::Emitter;
use tauri::State;

pub struct AppState {
    cancel: Arc<AtomicBool>,
    scanning: AtomicBool,
    dup_running: AtomicBool,
    last_scan: Mutex<Option<ScanResult>>,
    hash_cache: Arc<HashCache>,
}

impl Default for AppState {
    fn default() -> Self {
        AppState {
            cancel: Arc::new(AtomicBool::new(false)),
            scanning: AtomicBool::new(false),
            dup_running: AtomicBool::new(false),
            last_scan: Mutex::new(None),
            hash_cache: Arc::new(HashCache::new(HashMap::new())),
        }
    }
}

#[tauri::command]
async fn start_scan(
    state: State<'_, AppState>,
    window: tauri::Window,
    path: String,
) -> Result<ScanResult, String> {
    if state.dup_running.load(Ordering::SeqCst) {
        return Err("Идёт поиск дубликатов".into());
    }
    if state
        .scanning
        .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
        .is_err()
    {
        return Err("Сканирование уже запущено".into());
    }
    state.cancel.store(false, Ordering::SeqCst);

    let root = PathBuf::from(&path);
    if !root.is_dir() {
        state.scanning.store(false, Ordering::SeqCst);
        return Err("Указанная папка не существует".into());
    }

    let cancel = state.cancel.clone();

    let scan_win = window.clone();
    let scan_result = tauri::async_runtime::spawn_blocking(move || {
        let t0 = std::time::Instant::now();
        let make_progress = |win: &tauri::Window| -> scan::ProgressFn {
            let w = win.clone();
            Box::new(move |pct: u8| {
                let _ = w.emit("scan-progress", pct);
            })
        };
        #[cfg(target_os = "windows")]
        {
            let progress = make_progress(&scan_win);
            if let Some(mut res) = mft::scan_mft(&root, &cancel, progress) {
                res.elapsed_ms = t0.elapsed().as_millis() as u64;
                return Ok(res);
            }
        }
        let progress = make_progress(&scan_win);
        let mut res = scan::scan_root(&root, &cancel, progress)?;
        res.elapsed_ms = t0.elapsed().as_millis() as u64;
        Ok(res)
    })
    .await
    .map_err(|e| e.to_string())?;

    state.scanning.store(false, Ordering::SeqCst);

    match scan_result {
        Ok(res) => {
            *state.last_scan.lock().unwrap() = Some(res.clone());
            let _ = window.emit("scan-done", &res);
            Ok(res)
        }
        Err(e) => Err(e),
    }
}

#[tauri::command]
async fn find_duplicates(
    state: State<'_, AppState>,
    window: tauri::Window,
) -> Result<Vec<Vec<(u64, String)>>, String> {
    if state.scanning.load(Ordering::SeqCst) {
        return Err("Идёт сканирование".into());
    }
    if state
        .dup_running
        .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
        .is_err()
    {
        return Err("Поиск дубликатов уже запущен".into());
    }

    let candidates = {
        state
            .last_scan
            .lock()
            .unwrap()
            .as_ref()
            .map(|s| s.dup_candidates.clone())
            .unwrap_or_default()
    };

    if candidates.is_empty() {
        state.dup_running.store(false, Ordering::SeqCst);
        return Err("Сначала отсканируй папку на вкладке «Обзор»".into());
    }

    state.cancel.store(false, Ordering::SeqCst);

    let cache = state.hash_cache.clone();
    let cancel = state.cancel.clone();
    let status_win = window.clone();
    let total = candidates.len();

    let groups = tauri::async_runtime::spawn_blocking(move || {
        let _ = status_win.emit(
            "dup-progress",
            serde_json::json!({ "status": format!("Проверка {total} файлов...") }),
        );
        dup::find_duplicates(&candidates, &cache, &cancel)
    })
    .await
    .map_err(|e| e.to_string())?;

    state.dup_running.store(false, Ordering::SeqCst);
    Ok(groups)
}

#[tauri::command]
fn reveal_file(path: String) -> Result<(), String> {
    reveal::reveal_in_explorer(&path)
}

#[tauri::command]
fn select_folder(app: tauri::AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    let picked = app.dialog().file().blocking_pick_folder();
    Ok(picked
        .and_then(|fp| fp.into_path().ok())
        .map(|p| p.to_string_lossy().into_owned()))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![
            start_scan,
            find_duplicates,
            reveal_file,
            select_folder
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}