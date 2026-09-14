export class TabBar {
  readonly el: HTMLElement;
  private items: HTMLButtonElement[] = [];
  private slider: HTMLElement;
  private current = 0;
  private onChange: (index: number) => void;

  constructor(titles: string[], onChange: (index: number) => void) {
    this.onChange = onChange;

    const el = document.createElement("div");
    el.className = "tabbar";

    this.slider = document.createElement("div");
    this.slider.className = "tab-slider";
    el.appendChild(this.slider);

    titles.forEach((title, i) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "tab-item";
      item.textContent = title;
      item.addEventListener("click", () => this.setCurrent(i));
      el.appendChild(item);
      this.items.push(item);
    });

    this.el = el;
    this.applyState();
  }

  initSlider() {
    const item = this.items[this.current];
    if (!item || item.offsetWidth === 0) return;
    this.slider.style.transition = "none";
    this.slider.style.width = `${item.offsetWidth}px`;
    this.slider.style.left = `${item.offsetLeft}px`;
    void this.slider.offsetHeight;
    this.slider.style.transition = "";
  }

  private animateSlider() {
    const item = this.items[this.current];
    if (!item) return;
    this.slider.style.width = `${item.offsetWidth}px`;
    this.slider.style.left = `${item.offsetLeft}px`;
  }

  private applyState() {
    this.items.forEach((item, i) => {
      item.classList.toggle("active", i === this.current);
    });
  }

  setCurrent(index: number) {
    if (index < 0 || index >= this.items.length) return;
    const changed = index !== this.current;
    this.current = index;
    this.applyState();
    this.animateSlider();
    if (changed) this.onChange(index);
  }
}
