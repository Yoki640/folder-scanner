import {
  Chart,
  DoughnutController,
  ArcElement,
  Tooltip,
  type TooltipItem,
} from "chart.js";
import { formatSize } from "../utils";

Chart.register(DoughnutController, ArcElement, Tooltip);

const PALETTE = [
  "#FF5722",
  "#FFEB3B",
  "#03A9F4",
  "#4CAF50",
  "#9C27B0",
  "#E91E63",
  "#FF9800",
  "#8BC34A",
];

const MIN_SHARE = 0.02;
const MAX_SLICES = 7;

function pctStr(pct: number): string {
  if (pct <= 0) return "0%";
  if (pct < 0.1) return ">0%";
  return `${pct.toFixed(1)}%`;
}

export interface PieItem {
  name: string;
  value: number;
}

export class PieChart {
  private chart: Chart<"doughnut", number[], string>;
  private legendEl: HTMLElement;
  private rawData: number[] = [];
  private rawTotal = 0;

  constructor(canvas: HTMLCanvasElement, legendEl: HTMLElement) {
    this.legendEl = legendEl;
    this.chart = new Chart(canvas, {
      type: "doughnut",
      data: {
        labels: [],
        datasets: [
          {
            data: [],
            backgroundColor: [],
            borderColor: "transparent",
            borderWidth: 0,
            hoverOffset: 8,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "0%",
        animation: { duration: 300, easing: "easeOutCubic" },
        layout: {
          padding: 4,
        },
        plugins: {
          title: { display: false },
          legend: { display: false },
          tooltip: {
            backgroundColor: "#1a1a1e",
            titleColor: "#ffffff",
            bodyColor: "#cccccc",
            borderColor: "#333",
            borderWidth: 1,
            cornerRadius: 8,
            padding: 10,
            titleFont: { family: "'Inter', sans-serif", weight: "bold" as const },
            bodyFont: { family: "'Inter', sans-serif" },
            callbacks: {
              label: (item: TooltipItem<"doughnut">) => {
                const i = item.dataIndex;
                const val = this.rawData[i] ?? 0;
                const pct = this.rawTotal > 0 ? (val / this.rawTotal) * 100 : 0;
                return ` ${formatSize(val)} · ${pctStr(pct)}`;
              },
            },
          },
        },
      },
    });
  }

  private renderLegend(colors: string[], items: PieItem[]) {
    this.legendEl.textContent = "";
    items.forEach((item, i) => {
      const row = document.createElement("div");
      row.className = "chart-legend-item";
      const dot = document.createElement("span");
      dot.className = "chart-legend-dot";
      dot.style.backgroundColor = colors[i];
      const text = document.createElement("span");
      text.className = "chart-legend-text";
      const pct = this.rawTotal > 0 ? (item.value / this.rawTotal) * 100 : 0;
      text.textContent = `${item.name} · ${pctStr(pct)}`;
      row.append(dot, text);
      this.legendEl.appendChild(row);
    });
  }

  setData(items: PieItem[]) {
    const filtered = items.filter((i) => i.value > 0).sort((a, b) => b.value - a.value);
    if (filtered.length === 0) {
      this.clear();
      return;
    }

    const totalIn = filtered.reduce((a, b) => a + b.value, 0);
    const kept: PieItem[] = [];
    let other = 0;
    for (const item of filtered) {
      if (kept.length >= 3 && item.value / totalIn < MIN_SHARE) {
        other += item.value;
      } else {
        kept.push(item);
      }
    }
    while (kept.length > MAX_SLICES) {
      const last = kept.pop();
      if (last) other += last.value;
    }
    if (other > 0) kept.push({ name: "Остальное", value: other });

    this.rawData = kept.map((i) => i.value);
    this.rawTotal = kept.reduce((a, b) => a + b.value, 0);
    const colors = kept.map((_, i) => PALETTE[i % PALETTE.length]);
    this.chart.data.labels = kept.map((i) => i.name);
    this.chart.data.datasets[0].data = this.rawData;
    this.chart.data.datasets[0].backgroundColor = colors;
    this.chart.update();
    this.renderLegend(colors, kept);
  }

  clear() {
    this.rawData = [];
    this.rawTotal = 0;
    this.chart.data.labels = [];
    this.chart.data.datasets[0].data = [];
    this.chart.data.datasets[0].backgroundColor = [];
    this.chart.update();
    this.legendEl.textContent = "";
  }
}