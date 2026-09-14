use std::path::Path;

pub fn is_drive_root(path: &Path) -> bool {
    #[cfg(target_os = "windows")]
    {
        let s = path.to_string_lossy();
        let b = s.as_bytes();
        b.len() >= 3
            && b[0].is_ascii_alphabetic()
            && b[1] == b':'
            && (b[2] == b'\\' || b[2] == b'/')
            && b.len() <= 3
    }
    #[cfg(not(target_os = "windows"))]
    {
        path == Path::new("/")
    }
}

pub fn disk_usage(path: &Path) -> Option<(u64, u64)> {
    #[cfg(target_os = "windows")]
    let target: String = {
        let s = path.to_string_lossy();
        s.trim_end_matches(['\\', '/']).to_uppercase()
    };
    #[cfg(not(target_os = "windows"))]
    let target: String = path.to_string_lossy().into_owned();

    let disks = sysinfo::Disks::new_with_refreshed_list();
    for disk in disks.list() {
        let mp = disk
            .mount_point()
            .to_string_lossy()
            .trim_end_matches(['\\', '/'])
            .to_uppercase();
        if mp == target {
            return Some((disk.total_space(), disk.available_space()));
        }
    }
    None
}