import { el, formatSize, basename } from "../utils";
import type { DupGroups } from "../api";

export class DuplicatesTab {
  readonly el: HTMLElement;
  readonly findBtn: HTMLButtonElement;
  readonly statusLabel: HTMLElement;

  onFindRequested: (() => void) | null = null;
  onFileOpen: ((path: string) => void) | null = null;

  private busy = false;

  private heading: HTMLElement;
  private info: HTMLElement;
  private findBtnWrap: HTMLElement;
  private progressRow: HTMLElement;
  private progressBar: HTMLDivElement;
  private progressText: HTMLElement;
  private topSection: HTMLElement;
  private tableContainer: HTMLElement;
  private footer: HTMLElement;

  constructor() {
    const page = el("div", "tab-page dup-page");

    this.topSection = el("div", "dup-top-section");

    this.heading = el("div", "dup-heading", "Дубликаты в папке");
    this.topSection.appendChild(this.heading);

    this.info = el(
      "div",
      "dup-info",
      "Дубликаты — файлы, у которых совпадают имя, размер и содержимое.\n" +
        "Порог: файлы >= 1 МБ. Сначала отсканируй папку на вкладке «Обзор».\n" +
        "Некоторые файлы могут совпадать по содержимому намеренно — например, копии документов, резервные копии или системные дубликаты.\n" +
        "Двойной клик по файлу показывает его расположение в проводнике.",
    );
    this.topSection.appendChild(this.info);

    this.findBtnWrap = el("div");
    this.findBtn = el("button", "dup-find-btn", "Начать поиск дубликатов") as HTMLButtonElement;
    this.findBtn.type = "button";
    this.findBtnWrap.appendChild(this.findBtn);
    this.topSection.appendChild(this.findBtnWrap);

    this.progressRow = el("div", "dup-progress");
    const progressBox = el("div", "dup-progress-box");
    this.progressBar = el("div", "dup-progress-fill") as HTMLDivElement;
    progressBox.appendChild(this.progressBar);
    this.progressText = el("div", "dup-status", "");
    this.progressRow.append(progressBox, this.progressText);
    this.progressRow.style.display = "none";
    this.topSection.appendChild(this.progressRow);

    page.appendChild(this.topSection);

    this.tableContainer = el("div", "dup-table-container");
    page.appendChild(this.tableContainer);

    this.footer = el("div", "dup-footer");
    this.footer.style.display = "none";

    this.statusLabel = this.progressText;

    page.addEventListener("click", (e) => {
      if (e.target === this.findBtn) {
        if (this.onFindRequested) this.onFindRequested();
      }
    });
    page.addEventListener("dblclick", (e) => {
      const item = (e.target as HTMLElement).closest<HTMLElement>(".dup-row-item");
      if (item && item.dataset.path && this.onFileOpen) {
        this.onFileOpen(item.dataset.path);
      }
    });

    page.addEventListener(
      "wheel",
      (e) => {
        const wrap = this.tableContainer.querySelector<HTMLElement>(".dup-rows-wrap");
        if (!wrap) return;
        if (!(e.target as HTMLElement).closest(".dup-rows-wrap")) return;
        if (e.deltaY === 0) return;
        e.preventDefault();
        wrap.scrollTop += e.deltaY * 0.6;
      },
      { passive: false },
    );

    this.el = page;
  }

  setHeading(path: string) {
    this.heading.textContent = `Дубликаты в папке "${path}"`;
  }

  showProgress(show: boolean) {
    this.progressRow.style.display = show ? "flex" : "none";
  }

  setProgress(pct: number) {
    this.progressBar.style.width = `${Math.max(0, Math.min(100, pct))}%`;
  }

  setGroups(groups: DupGroups) {
    this.tableContainer.textContent = "";

    let totalWasted = 0;

    if (groups.length === 0) {
      const empty = el("div", "dup-empty", "В этой папке дубликатов нет.");
      this.tableContainer.appendChild(empty);
      this.footer.style.display = "none";
      this.statusLabel.textContent = "дубликатов не найдено";
      return;
    }

    const tableCard = el("div", "dup-table-card");

    const header = el("div", "dup-table-header");
    header.innerHTML = '<span>Файл</span><span>Размер</span><span>Путь</span>';
    tableCard.appendChild(header);

    const rowsWrap = el("div", "dup-rows-wrap");

    groups.forEach((group) => {
      const size = group[0][0];
      const wasted = size * (group.length - 1);
      totalWasted += wasted;

      const groupHeader = el("div", "dup-group-header", `${group.length} копии - ${basename(group[0][1])}`);
      rowsWrap.appendChild(groupHeader);

      group.forEach(([s, path]) => {
        const rowItem = el("div", "dup-row-item");
        const nameSpan = el("span", "dup-item-name", basename(path));
        const sizeSpan = el("span", "dup-item-size", formatSize(s));
        const dirSpan = el("span", "dup-item-path", path.split(/[\\/]/).slice(0, -1).join("/"));
        rowItem.append(nameSpan, sizeSpan, dirSpan);
        rowItem.dataset.path = path;
        rowsWrap.appendChild(rowItem);
      });
    });

    tableCard.appendChild(rowsWrap);
    tableCard.appendChild(this.footer);
    this.tableContainer.appendChild(tableCard);

    this.footer.textContent = `Всего групп: ${groups.length}  ·  Можно освободить: ${formatSize(totalWasted)}`;
    this.footer.style.display = "block";
    this.statusLabel.textContent =
      `групп: ${groups.length}  ·  можно освободить: ${formatSize(totalWasted)}`;
    this.applyDisabled();
  }

  setStatus(text: string) {
    this.statusLabel.textContent = text;
  }

  setBusy(busy: boolean) {
    this.busy = busy;
    this.applyDisabled();
  }

  private applyDisabled() {
    this.findBtn.disabled = this.busy;
  }

  clearTree() {
    this.tableContainer.textContent = "";
    this.footer.style.display = "none";
    this.progressBar.style.width = "0%";
  }
}