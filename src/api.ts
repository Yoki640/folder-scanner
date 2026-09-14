import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

export interface ScanResult {
  total_size: number;
  total_files: number;
  total_folders: number;
  folder_sizes: Record<string, number>;
  extension_sizes: Record<string, number>;
  top_files: Array<[number, string]>;
  dup_candidates: Array<[number, string]>;
  system_skipped: boolean;
  has_files: boolean;
  disk_total: number | null;
  disk_free: number | null;
  fast_scan: boolean;
  mode: string;
  root_path: string;
  elapsed_ms: number;
}

export type DupGroups = Array<Array<[number, string]>>;

export const api = {
  startScan: (path: string) => invoke<ScanResult>("start_scan", { path }),
  findDuplicates: () => invoke<DupGroups>("find_duplicates"),
  revealFile: (path: string) => invoke<void>("reveal_file", { path }),
  selectFolder: () => invoke<string | null>("select_folder"),
};

export function onScanProgress(cb: (pct: number) => void): Promise<UnlistenFn> {
  return listen<number>("scan-progress", (e) => cb(e.payload));
}

export function onScanDone(cb: (result: ScanResult) => void): Promise<UnlistenFn> {
  return listen<ScanResult>("scan-done", (e) => cb(e.payload));
}

export function onDupProgress(cb: (status: string) => void): Promise<UnlistenFn> {
  return listen<{ status: string }>("dup-progress", (e) => cb(e.payload.status));
}