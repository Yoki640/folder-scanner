#[cfg(target_os = "windows")]
/// Открывает Проводник и выделяет файл/папку.
/// Использует штатный Windows Shell API `SHOpenFolderAndSelectItems` —
/// не запускает `explorer.exe` как процесс вручную, поэтому
/// антивирусы (360 Total Security и др.) не реагируют.
pub fn reveal_in_explorer(path: &str) -> Result<(), String> {
    use windows::core::PCWSTR;
    use windows::Win32::System::Com::{CoInitializeEx, CoUninitialize, COINIT_APARTMENTTHREADED};
    use windows::Win32::UI::Shell::{ILCreateFromPathW, ILFree, SHOpenFolderAndSelectItems};

    unsafe {
        let _ = CoInitializeEx(None, COINIT_APARTMENTTHREADED);

        let wide = path
            .encode_utf16()
            .chain(std::iter::once(0))
            .collect::<Vec<u16>>();
        let pidl = ILCreateFromPathW(PCWSTR(wide.as_ptr()));

        let hr = if pidl.is_null() {
            windows::core::HRESULT(-1)
        } else {
            let r = SHOpenFolderAndSelectItems(pidl, None, 0);
            ILFree(Some(pidl));
            r.into()
        };
        CoUninitialize();

        if hr.is_ok() {
            return Ok(());
        }

        // Fallback: открываем родительскую папку через explore-verb
        use windows::Win32::UI::Shell::ShellExecuteW;
        use windows::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;
        if let Some(parent) = std::path::Path::new(path).parent() {
            let mut v = "explore\0".encode_utf16().collect::<Vec<u16>>();
            let pw = parent
                .to_string_lossy()
                .encode_utf16()
                .chain(std::iter::once(0))
                .collect::<Vec<u16>>();
            let op = PCWSTR(v.as_mut_ptr());
            let _ = ShellExecuteW(None, op, PCWSTR(pw.as_ptr()), None, None, SW_SHOWNORMAL);
        }
        Ok(())
    }
}

#[cfg(target_os = "macos")]
pub fn reveal_in_explorer(path: &str) -> Result<(), String> {
    std::process::Command::new("open")
        .arg("-R")
        .arg(path)
        .spawn()
        .map(|_| ())
        .map_err(|e| e.to_string())
}

#[cfg(target_os = "linux")]
pub fn reveal_in_explorer(path: &str) -> Result<(), String> {
    for cmd in [
        ("nautilus", vec!["--select", path]),
        ("dolphin", vec!["--select", path]),
        ("thunar", vec!["--select", path]),
    ] {
        if std::process::Command::new(cmd.0)
            .args(&cmd.1)
            .spawn()
            .is_ok()
        {
            return Ok(());
        }
    }
    let parent = std::path::Path::new(path)
        .parent()
        .map(|p| p.to_string_lossy().into_owned())
        .unwrap_or_else(|| "/".to_string());
    std::process::Command::new("xdg-open")
        .arg(parent)
        .spawn()
        .map(|_| ())
        .map_err(|e| e.to_string())
}

#[cfg(not(any(target_os = "windows", target_os = "macos", target_os = "linux")))]
pub fn reveal_in_explorer(path: &str) -> Result<(), String> {
    let _ = path;
    Err("Не поддерживается".to_string())
}