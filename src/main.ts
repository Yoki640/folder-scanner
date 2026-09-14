import "./styles/global.css";
import "./styles/components.css";

import { TitleBar } from "./components/TitleBar";
import { TabBar } from "./components/TabBar";
import { OverviewTab } from "./components/OverviewTab";
import { DuplicatesTab } from "./components/DuplicatesTab";
import { ConfirmDialog } from "./components/ConfirmDialog";
import {
  api,
  onScanProgress,
  onScanDone,
  onDupProgress,
  type ScanResult,
} from "./api";

class AppController {
  private container!: HTMLElement;
  private inner!: HTMLElement;
  private contentFrame!: HTMLElement;
  private tabBar!: TabBar;
  private headerRow!: HTMLElement;
  private newScanBtn!: HTMLButtonElement;

  private overview!: OverviewTab;
  private dups!: DuplicatesTab;
  private dialog!: ConfirmDialog;

  private scanning = false;
  private dupRunning = false;
  private lastResult: ScanResult | null = null;
  private dupTimer: ReturnType<typeof setInterval> | null = null;

  constructor() {
    const root = document.getElementById("app");
    if (!root) return;
    root.textContent = "";

    this.container = document.createElement("div");
    this.container.className = "container";

    const titleBar = new TitleBar();

    this.inner = document.createElement("div");
    this.inner.className = "inner";

    // Header row with tabs and new-scan button
    this.headerRow = document.createElement("div");
    this.headerRow.className = "header-row hidden";

    this.contentFrame = document.createElement("div");
    this.contentFrame.className = "content-frame";

    this.overview = new OverviewTab();
    this.dups = new DuplicatesTab();
    this.contentFrame.append(this.overview.el, this.dups.el);

    this.dialog = new ConfirmDialog();

    this.tabBar = new TabBar(["Обзор", "Дубликаты файлов"], (index) => {
      this.overview.el.classList.toggle("active", index === 0);
      this.dups.el.classList.toggle("active", index === 1);
    });

    this.newScanBtn = document.createElement("button");
    this.newScanBtn.className = "new-scan-btn";
    this.newScanBtn.textContent = "Сканировать новую папку";
    this.newScanBtn.addEventListener("click", () => this.requestNewScan());

    this.headerRow.append(this.tabBar.el, this.newScanBtn);
    this.inner.append(this.headerRow, this.contentFrame);
    this.container.append(titleBar.el, this.inner, this.dialog.el);
    root.appendChild(this.container);

    this.overview.el.classList.add("active");
    this.wire();
  }

  private wire() {
    this.overview.onScanRequested = (p) => this.requestScan(p);
    this.overview.onSelectFolder = () => this.selectFolder();
    this.overview.onTopFileOpen = (p) => this.reveal(p);
    this.dups.onFindRequested = () => this.findDuplicates();
    this.dups.onFileOpen = (p) => this.reveal(p);

    onScanProgress((pct) => {
      if (this.scanning) {
        this.overview.setProgress(pct);
      }
    });
    onScanDone((result) => {
      if (!this.scanning) return;
      this.scanning = false;
      this.overview.setBusy(false);
      this.overview.setProgress(100);
      this.renderScanResult(result);
    });
    onDupProgress((status) => {
      if (this.dupRunning) this.dups.setStatus(status);
    });

    // Start on initial screen
    this.showHeader(false);
  }

  private showHeader(show: boolean) {
    this.headerRow.classList.toggle("hidden", !show);
    if (show) {
      requestAnimationFrame(() => this.tabBar.initSlider());
    }
  }

  private currentOp(): string {
    if (this.scanning) return "сканирование";
    if (this.dupRunning) return "поиск дубликатов";
    return "";
  }

  private showBusyDialog() {
    const op = this.currentOp();
    this.dialog.show({
      title: "Подождите",
      message: op ? `Идёт ${op}...` : "Операция ещё выполняется...",
      details: "Дождитесь завершения текущей операции, прежде чем запускать новую.",
      yesText: "ОК",
      single: true,
    });
  }

  private requestNewScan() {
    if (this.scanning || this.dupRunning) {
      this.showBusyDialog();
      return;
    }
    this.overview.reset();
    this.dups.clearTree();
    this.tabBar.setCurrent(0);
    this.showHeader(false);
  }

  private requestScan(rawPath: string) {
    const path = rawPath.trim();
    if (!path) return;
    if (this.scanning || this.dupRunning) {
      this.showBusyDialog();
      return;
    }
    this.lastResult = null;
    this.scanning = true;
    this.overview.clearAll();
    this.overview.setBusy(true);
    this.dups.clearTree();
    this.dups.setHeading(path);
    this.showHeader(true);
    api
      .startScan(path)
      .then(() => {
        /* результат придёт через событие scan-done */
      })
      .catch((err) => this.onScanError(String(err)));
  }

  private onScanError(_message: string) {
    if (!this.scanning) return;
    this.scanning = false;
    this.overview.setBusy(false);
    this.overview.showInitialState();
  }

  private renderScanResult(result: ScanResult) {
    this.lastResult = result;
    this.overview.setStats({
      total_size: result.total_size,
      total_files: result.total_files,
      total_folders: result.total_folders,
      elapsed_ms: result.elapsed_ms,
      disk_total: result.disk_total,
      disk_free: result.disk_free,
    });

    this.overview.hideEmptyNotice();

    if (result.total_files === 0 && result.total_folders === 0) {
      this.overview.showEmptyNotice();
    } else {
      this.overview.setCharts(
        Object.entries(result.folder_sizes),
        Object.entries(result.extension_sizes),
      );
      this.overview.setTopFiles(result.top_files);
    }
    this.overview.showResults();

    if (result.dup_candidates.length === 0) {
      this.dups.setStatus("Кандидаты на дубликаты не найдены.");
    } else {
      this.dups.setStatus(`Кандидатов на дубликаты: ${result.dup_candidates.length}`);
    }
  }

  private findDuplicates() {
    if (this.scanning) {
      this.showBusyDialog();
      return;
    }
    if (this.dupRunning) return;
    if (!this.lastResult) {
      this.dups.setStatus("Нет данных. Сначала отсканируйте папку.");
      return;
    }
    if (!this.lastResult.has_files || this.lastResult.dup_candidates.length === 0) {
      this.dups.setGroups([]);
      this.dups.setBusy(false);
      return;
    }
    this.dupRunning = true;
    this.dups.clearTree();
    this.dups.setBusy(true);
    this.dups.showProgress(true);
    this.dups.setProgress(10);
    this.dups.setStatus("Ищу дубликаты файлов...");
    let dupPct = 10;
    this.dupTimer = setInterval(() => {
      if (dupPct < 85) {
        dupPct += 3;
        this.dups.setProgress(dupPct);
      }
    }, 200);
    api
      .findDuplicates()
      .then((groups) => {
        if (this.dupTimer) { clearInterval(this.dupTimer); this.dupTimer = null; }
        this.dupRunning = false;
        this.dups.setProgress(100);
        this.dups.showProgress(false);
        this.dups.setGroups(groups);
        this.dups.setBusy(false);
      })
      .catch((err) => {
        if (this.dupTimer) { clearInterval(this.dupTimer); this.dupTimer = null; }
        this.dupRunning = false;
        this.dups.showProgress(false);
        this.dups.setStatus(`Ошибка: ${String(err)}`);
        this.dups.setBusy(false);
      });
  }

  private selectFolder() {
    if (this.scanning || this.dupRunning) {
      this.showBusyDialog();
      return;
    }
    api
      .selectFolder()
      .then((path) => {
        if (path) this.overview.pathInput.value = path;
      })
      .catch(() => {
        /* закрыт диалог */
      });
  }

  private reveal(path: string) {
    api.revealFile(path).catch(() => {
      /* ignore */
    });
  }
}

new AppController();
