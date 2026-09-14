import { getCurrentWindow } from "@tauri-apps/api/window";

function makeButton(label: string, onClick: () => void): HTMLButtonElement {
  const b = document.createElement("button");
  b.className = "titlebar-btn";
  b.type = "button";
  b.textContent = label;
  b.addEventListener("click", onClick);
  return b;
}

export class TitleBar {
  readonly el: HTMLElement;
  private maxBtn: HTMLButtonElement;
  private appWindow = getCurrentWindow();

  constructor() {
    const el = document.createElement("div");
    el.className = "titlebar";
    el.innerHTML = `
      <span class="titlebar-title">Сканер папок</span>
      <div class="titlebar-spacer"></div>
    `;

    const minBtn = makeButton("─", () => this.appWindow.minimize());
    this.maxBtn = makeButton("☐", () => void this.toggleMaximize());
    const closeBtn = makeButton("✕", () => this.appWindow.close());
    closeBtn.classList.add("close");

    el.append(minBtn, this.maxBtn, closeBtn);

    el.addEventListener("mousedown", (e) => {
      const target = e.target as HTMLElement;
      if (target.closest(".titlebar-btn")) return;
      if (e.button === 0 && e.detail === 1) {
        void this.appWindow.startDragging();
      }
    });
    el.addEventListener("dblclick", (e) => {
      const target = e.target as HTMLElement;
      if (target.closest(".titlebar-btn")) return;
      void this.toggleMaximize();
    });

    this.el = el;
    void this.syncMaxIcon();
  }

  private async toggleMaximize() {
    await this.appWindow.toggleMaximize();
    await this.syncMaxIcon();
  }

  private async syncMaxIcon() {
    try {
      const maximized = await this.appWindow.isMaximized();
      this.maxBtn.textContent = maximized ? "❐" : "☐";
    } catch {
      /* ignore */
    }
  }
}
