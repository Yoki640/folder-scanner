import { PieChart } from "./PieChart";
import { el, formatSize } from "../utils";

export class OverviewTab {
  readonly el: HTMLElement;
  readonly pathInput: HTMLInputElement;
  readonly scanBtn: HTMLButtonElement;
  readonly scanOverlay: HTMLDivElement;
  readonly progressBar: HTMLDivElement;
  readonly folderChart: PieChart;
  readonly fileChart: PieChart;

  onScanRequested: ((path: string) => void) | null = null;
  onSelectFolder: (() => void) | null = null;
  onTopFileOpen: ((path: string) => void) | null = null;

  private initialScreen: HTMLElement;
  private scanState: HTMLElement;
  private resultsState: HTMLElement;
  private progressText: HTMLElement;
  private statsCard: HTMLElement;
  private topList: HTMLElement;
  private folderCanvas: HTMLCanvasElement;
  private fileCanvas: HTMLCanvasElement;
  private emptyNotice: HTMLElement;

  constructor() {
    const page = el("div", "tab-page overview-page");

    this.initialScreen = el("div", "initial-screen");
    const initTitle = el("div", "initial-title", "Введите путь к папке для сканирования");
    const initSubtitle = el("div", "initial-subtitle", "Или откройте папку через кнопку");
    this.pathInput = el("input", "initial-input") as HTMLInputElement;
    this.pathInput.placeholder = "Введите путь...";
    this.pathInput.type = "text";
    const selectBtn = el("button", "initial-btn", "Выбрать папку") as HTMLButtonElement;
    selectBtn.type = "button";
    selectBtn.addEventListener("click", () => {
      if (this.onSelectFolder) this.onSelectFolder();
    });
    this.scanBtn = el("button", "initial-btn initial-btn-scan", "Сканировать папку") as HTMLButtonElement;
    this.scanBtn.type = "button";
    this.scanOverlay = el("div", "scan-overlay");
    this.scanBtn.appendChild(this.scanOverlay);
    this.initialScreen.append(initTitle, initSubtitle, this.pathInput, selectBtn, this.scanBtn);
    page.appendChild(this.initialScreen);

    this.scanState = el("div", "scan-state");
    this.scanState.style.display = "none";
    const scanSubtitle = el("div", "scan-subtitle");
    this.progressText = el("div", "progress-text", "Сканирую папку...");
    const progressRow = el("div", "progress-row");
    const progressBox = el("div", "progress-box");
    this.progressBar = el("div", "progress-bar");
    progressBox.appendChild(this.progressBar);
    progressRow.appendChild(progressBox);
    this.scanState.append(scanSubtitle, progressRow, this.progressText);
    page.appendChild(this.scanState);

    this.resultsState = el("div", "results-state");
    this.resultsState.style.display = "none";
    const resultsHeading = el("div", "results-heading");
    const resultsGrid = el("div", "results-grid");

    const folderCard = el("div", "card chart-card");
    const folderTitle = el("div", "card-title", "Диаграмма папок");
    const folderBody = el("div", "chart-body");
    const folderWrap = el("div", "chart-canvas-wrap");
    this.folderCanvas = el("canvas", "chart-canvas") as HTMLCanvasElement;
    const folderLegend = el("div", "chart-legend");
    folderWrap.appendChild(this.folderCanvas);
    folderBody.append(folderWrap, folderLegend);
    folderCard.append(folderTitle, folderBody);

    const fileCard = el("div", "card chart-card");
    const fileTitle = el("div", "card-title", "Диаграмма расширений");
    const fileBody = el("div", "chart-body");
    const fileWrap = el("div", "chart-canvas-wrap");
    this.fileCanvas = el("canvas", "chart-canvas") as HTMLCanvasElement;
    const fileLegend = el("div", "chart-legend");
    fileWrap.appendChild(this.fileCanvas);
    fileBody.append(fileWrap, fileLegend);
    fileCard.append(fileTitle, fileBody);

    resultsGrid.append(folderCard, fileCard);

    this.statsCard = el("div", "card stats-card");
    const statsTitle = el("div", "card-title", "Результаты сканирования");
    this.statsCard.appendChild(statsTitle);

    const topCard = el("div", "card top-card");
    const topTitle = el("div", "card-title", "Топ-5 больших файлов");
    this.topList = el("div", "top-list");
    topCard.append(topTitle, this.topList);

    resultsGrid.append(this.statsCard, topCard);

    this.emptyNotice = el("div", "overview-empty", "Папка пуста");
    this.emptyNotice.style.display = "none";
    this.resultsState.append(resultsHeading, resultsGrid, this.emptyNotice);
    page.appendChild(this.resultsState);

    this.folderChart = new PieChart(this.folderCanvas, folderLegend);
    this.fileChart = new PieChart(this.fileCanvas, fileLegend);

    this.scanBtn.addEventListener("click", () => {
      if (!this.scanOverlay.contains(document.activeElement)) {
        if (this.onScanRequested) this.onScanRequested(this.pathInput.value);
      }
    });
    this.pathInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        if (this.onScanRequested) this.onScanRequested(this.pathInput.value);
      }
    });
    this.topList.addEventListener("dblclick", (e) => {
      const row = (e.target as HTMLElement).closest<HTMLElement>(".top-file-row");
      if (row && row.dataset.path && this.onTopFileOpen) {
        this.onTopFileOpen(row.dataset.path);
      }
    });

    this.el = page;
  }

  setBusy(busy: boolean) {
    this.scanBtn.classList.toggle("busy", busy);
    this.scanOverlay.classList.toggle("active", busy);
    this.pathInput.disabled = busy;
    if (busy) this.showScanState();
  }

  setProgress(pct: number) {
    this.progressBar.style.width = `${Math.max(0, Math.min(100, pct))}%`;
  }

  showInitialState() {
    this.initialScreen.style.display = "flex";
    this.scanState.style.display = "none";
    this.resultsState.style.display = "none";
  }

  showScanState() {
    this.initialScreen.style.display = "none";
    this.scanState.style.display = "flex";
    this.resultsState.style.display = "none";
    const subtitle = this.scanState.querySelector(".scan-subtitle");
    if (subtitle) subtitle.textContent = `Обзор папки "${this.pathInput.value}"`;
  }

  showResults() {
    this.initialScreen.style.display = "none";
    this.scanState.style.display = "none";
    this.resultsState.style.display = "flex";
  }

  setStats(result: {
    total_size: number;
    total_files: number;
    total_folders: number;
    elapsed_ms: number;
    disk_total: number | null;
    disk_free: number | null;
  }) {
    this.statsCard.innerHTML = "";
    const statsTitle = el("div", "card-title", "Результаты сканирования");
    this.statsCard.appendChild(statsTitle);

    let timeStr: string;
    if (result.elapsed_ms < 1000) {
      timeStr = `${Math.round(result.elapsed_ms)} мс`;
    } else {
      timeStr = `${(result.elapsed_ms / 1000).toFixed(1)} сек`;
    }

    const stats = [
      { label: "Папок:", value: String(result.total_folders) },
      { label: "Файлов:", value: String(result.total_files) },
      { label: "Размер просканированных файлов:", value: formatSize(result.total_size) },
      { label: "Время сканирования:", value: timeStr },
    ];

    if (result.disk_total != null) {
      stats.push({ label: "Всего на диске:", value: formatSize(result.disk_total) });
    }
    if (result.disk_free != null) {
      stats.push({ label: "Свободно на диске:", value: formatSize(result.disk_free) });
    }

    for (const stat of stats) {
      const row = el("div", "stat-row");
      const label = el("span", "stat-label", stat.label);
      const value = el("span", "stat-value", stat.value);
      row.append(label, value);
      this.statsCard.appendChild(row);
    }

    const heading = this.resultsState.querySelector(".results-heading");
    if (heading) heading.textContent = `Обзор папки "${this.pathInput.value}"`;
  }

  showEmptyNotice() {
    this.emptyNotice.textContent = "Папка пуста";
    this.emptyNotice.style.display = "block";
    this.resultsState.querySelector(".results-grid")?.setAttribute("style", "display:none");
  }

  hideEmptyNotice() {
    this.emptyNotice.style.display = "none";
    const grid = this.resultsState.querySelector<HTMLElement>(".results-grid");
    if (grid) grid.style.display = "";
  }

  setTopFiles(files: Array<[number, string]>) {
    this.topList.textContent = "";
    const top5 = files.slice(0, 5);
    for (const [size, path] of top5) {
      const row = el("div", "top-file-row");
      const sizeSpan = el("span", "top-file-size", formatSize(size));
      const pathSpan = el("span", "top-file-path", path);
      row.append(sizeSpan, pathSpan);
      row.dataset.path = path;
      this.topList.appendChild(row);
    }
  }

  setCharts(folders: [string, number][], extensions: [string, number][]) {
    this.folderChart.setData(folders.map(([n, v]) => ({ name: n, value: v })));
    this.fileChart.setData(
      extensions.map(([n, v]) => ({ name: n ? `.${n}` : "(без расширения)", value: v })),
    );
  }

  clearAll() {
    this.folderChart.clear();
    this.fileChart.clear();
    this.setProgress(0);
  }

  reset() {
    this.clearAll();
    this.showInitialState();
  }
}
