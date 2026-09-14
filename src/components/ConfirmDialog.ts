import { el } from "../utils";

interface DialogOptions {
  title: string;
  message: string;
  details?: string;
  yesText?: string;
  single?: boolean;
  onYes?: () => void;
}

export class ConfirmDialog {
  readonly el: HTMLElement;
  private titleEl: HTMLElement;
  private messageEl: HTMLElement;
  private detailsEl: HTMLElement;
  private yesBtn: HTMLButtonElement;
  private noBtn: HTMLButtonElement;
  private onYes: (() => void) | null = null;

  constructor() {
    const overlay = el("div", "dialog-overlay");
    const box = el("div", "dialog-box");
    this.titleEl = el("div", "dialog-title");
    this.messageEl = el("div", "dialog-message");
    this.detailsEl = el("div", "dialog-details");
    const btnRow = el("div", "dialog-buttons");
    this.noBtn = el("button", "btn-no", "Отмена") as HTMLButtonElement;
    this.noBtn.type = "button";
    this.yesBtn = el("button", "btn-yes", "Удалить") as HTMLButtonElement;
    this.yesBtn.type = "button";
    btnRow.append(this.noBtn, this.yesBtn);
    box.append(this.titleEl, this.messageEl, this.detailsEl, btnRow);
    overlay.appendChild(box);
    this.el = overlay;

    this.noBtn.addEventListener("click", () => this.hide());
    this.yesBtn.addEventListener("click", () => {
      const cb = this.onYes;
      this.hide();
      if (cb) cb();
    });
  }

  show(options: DialogOptions) {
    this.titleEl.textContent = options.title;
    this.messageEl.textContent = options.message;
    this.detailsEl.textContent = options.details ?? "";
    this.detailsEl.style.display = options.details ? "" : "none";
    this.yesBtn.textContent = options.yesText ?? "Удалить";
    this.noBtn.style.display = options.single ? "none" : "";
    this.onYes = options.onYes ?? null;
    this.el.classList.add("visible");
  }

  hide() {
    this.el.classList.remove("visible");
    this.onYes = null;
  }
}