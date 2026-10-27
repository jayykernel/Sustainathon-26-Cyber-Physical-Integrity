import type { TimelineSample } from "../sim/timeline";
import { COLORS } from "../tokens";
import { classificationLabel, formatSimTime } from "./format";

const PAD = { left: 27, right: 48, top: 14, bottom: 16 };
const FONT = '9px "IBM Plex Sans", "Segoe UI", system-ui, sans-serif';

function withAlpha(hex: string, alpha: number): string {
  const value = Number.parseInt(hex.slice(1), 16);
  const red = (value >> 16) & 255;
  const green = (value >> 8) & 255;
  const blue = value & 255;
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

/** Live strip chart for samples received from the backend WebSocket. */
export class TemperatureChart {
  private readonly ctx: CanvasRenderingContext2D;
  private readonly samples: TimelineSample[] = [];
  private readonly observer: ResizeObserver;
  private readonly tooltip: HTMLElement;
  private readonly divergence: HTMLElement;
  private width = 0;
  private height = 0;
  private hoverX: number | null = null;

  constructor(private readonly canvas: HTMLCanvasElement) {
    const context = canvas.getContext("2d");
    if (!context) throw new Error("The temperature chart could not get a 2D context");
    this.ctx = context;
    this.tooltip = document.getElementById("chart-tooltip") as HTMLElement;
    this.divergence = document.getElementById("chart-divergence") as HTMLElement;
    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(canvas);
    canvas.addEventListener("pointermove", (event) => this.showAtPointer(event));
    canvas.addEventListener("pointerleave", () => {
      this.hoverX = null;
      this.tooltip.hidden = true;
      this.draw();
    });
    canvas.addEventListener("focus", () => {
      const latest = this.samples.at(-1);
      if (latest) this.showSample(latest, this.width - PAD.right - 2, PAD.top + 4);
    });
    canvas.addEventListener("blur", () => { this.tooltip.hidden = true; this.hoverX = null; this.draw(); });
    this.resize();
    this.draw();
  }

  reset(): void {
    this.samples.length = 0;
    this.hoverX = null;
    this.tooltip.hidden = true;
    this.divergence.dataset.state = "aligned";
    this.divergence.textContent = "Waiting for telemetry";
    this.draw();
  }

  resize(): void {
    const rect = this.canvas.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.width = rect.width;
    this.height = rect.height;
    this.canvas.width = Math.max(1, Math.round(rect.width * dpr));
    this.canvas.height = Math.max(1, Math.round(rect.height * dpr));
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.draw();
  }

  render(sample: TimelineSample): void {
    const last = this.samples[this.samples.length - 1];
    if (last && sample.t <= last.t) {
      if (sample.t < last.t) this.samples.length = 0;
      else this.samples.pop();
    }
    this.samples.push(sample);
    if (this.samples.length > 3601) this.samples.splice(0, this.samples.length - 3601);
    this.draw();
  }

  private draw(): void {
    if (this.width <= 0 || this.height <= 0) return;
    const ctx = this.ctx;
    const left = PAD.left, right = this.width - PAD.right;
    const top = PAD.top, bottom = this.height - PAD.bottom;
    const plotWidth = Math.max(1, right - left), plotHeight = Math.max(1, bottom - top);
    const duration = Math.max(600, this.samples.at(-1)?.duration_s ?? 3600);
    const allTemps = this.samples.flatMap((sample) => [sample.trueTempC, sample.reportedTempC, sample.modelTempC]);
    const low = Math.min(30, ...allTemps) - 1, high = Math.max(60, ...allTemps) + 1;
    const x = (time: number) => left + (time / duration) * plotWidth;
    const y = (temp: number) => bottom - ((temp - low) / (high - low)) * plotHeight;

    ctx.clearRect(0, 0, this.width, this.height);
    const latest = this.samples.at(-1);
    if (latest) {
      const divergence = latest.reportedTempC - latest.modelTempC;
      const divergent = Math.abs(divergence) >= 1;
      this.divergence.dataset.state = divergent ? "divergence" : "aligned";
      this.divergence.textContent = divergent ? `DIVERGENCE ${divergence >= 0 ? "+" : ""}${divergence.toFixed(1)} C` : "Signals aligned";
    }
    ctx.font = FONT;
    ctx.lineWidth = 1;
    ctx.strokeStyle = COLORS.rule;
    ctx.fillStyle = COLORS.inkSoft;
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (const temp of [35, 45, 55]) {
      const py = y(temp);
      ctx.beginPath(); ctx.moveTo(left, py); ctx.lineTo(right, py); ctx.stroke();
      ctx.fillText(String(temp), left - 5, py);
    }
    ctx.strokeStyle = COLORS.caution;
    ctx.setLineDash([4, 3]);
    ctx.beginPath(); ctx.moveTo(left, y(55)); ctx.lineTo(right, y(55)); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = COLORS.caution;
    ctx.textAlign = "right";
    ctx.textBaseline = "bottom";
    ctx.fillText("55 C LIMIT", right, y(55) - 3);
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (const fraction of [0, 0.25, 0.5, 0.75, 1]) {
      const time = duration * fraction;
      const px = x(time);
      ctx.strokeStyle = COLORS.rule;
      ctx.beginPath(); ctx.moveTo(px, top); ctx.lineTo(px, bottom); ctx.stroke();
      ctx.fillStyle = COLORS.inkSoft;
      ctx.fillText(formatSimTime(time), px, bottom + 4);
    }
    ctx.save(); ctx.beginPath(); ctx.rect(left, top, plotWidth, plotHeight); ctx.clip();
    for (let index = 1; index < this.samples.length; index += 1) {
      const previous = this.samples[index - 1];
      const current = this.samples[index];
      if (Math.abs(previous.reportedTempC - previous.modelTempC) < 1 && Math.abs(current.reportedTempC - current.modelTempC) < 1) continue;
      ctx.beginPath();
      ctx.moveTo(x(previous.t), y(previous.reportedTempC));
      ctx.lineTo(x(current.t), y(current.reportedTempC));
      ctx.lineTo(x(current.t), y(current.modelTempC));
      ctx.lineTo(x(previous.t), y(previous.modelTempC));
      ctx.closePath();
      ctx.fillStyle = withAlpha(COLORS.hazard, 0.1);
      ctx.fill();
    }
    const trace = (pick: (sample: TimelineSample) => number) => {
      if (this.samples.length === 0) return;
      const first = this.samples[0];
      ctx.moveTo(x(first.t), y(pick(first)));
      for (let index = 1; index < this.samples.length; index += 1) {
        const previous = this.samples[index - 1];
        const current = this.samples[index];
        const middleX = (x(previous.t) + x(current.t)) / 2;
        const middleY = (y(pick(previous)) + y(pick(current))) / 2;
        ctx.quadraticCurveTo(x(previous.t), y(pick(previous)), middleX, middleY);
      }
      const last = this.samples[this.samples.length - 1];
      ctx.lineTo(x(last.t), y(pick(last)));
    };
    const line = (pick: (sample: TimelineSample) => number, color: string, width: number, dash: number[] = []) => {
      if (this.samples.length < 1) return;
      ctx.beginPath(); trace(pick);
      ctx.strokeStyle = color; ctx.lineWidth = width; ctx.setLineDash(dash); ctx.stroke(); ctx.setLineDash([]);
    };
    line((sample) => sample.reportedTempC, COLORS.inkSoft, 1.2, [5, 3]);
    line((sample) => sample.modelTempC, COLORS.protected, 1.0);
    line((sample) => sample.trueTempC, COLORS.hazard, 1.8);
    ctx.restore();

    if (latest) {
      ctx.fillStyle = COLORS.ink;
      ctx.beginPath(); ctx.arc(x(latest.t), y(latest.trueTempC), 2, 0, Math.PI * 2); ctx.fill();
      ctx.font = FONT; ctx.textAlign = "left"; ctx.textBaseline = "middle";
      ctx.fillStyle = COLORS.hazard; ctx.fillText("TRUE", right + 4, y(latest.trueTempC));
      ctx.fillStyle = COLORS.inkSoft; ctx.fillText("REPORTED", right + 4, y(latest.reportedTempC));
      ctx.fillStyle = COLORS.protected; ctx.fillText("MODEL", right + 4, y(latest.modelTempC));
      this.canvas.setAttribute("aria-label", `Live backend temperature at ${formatSimTime(latest.t)}. True ${latest.trueTempC.toFixed(1)} degrees Celsius. Reported ${latest.reportedTempC.toFixed(1)}. Model estimate ${latest.modelTempC.toFixed(1)}. Classifier ${classificationLabel(latest.classification)}.`);
    }
    if (this.hoverX !== null) {
      ctx.save();
      ctx.strokeStyle = COLORS.inkSoft;
      ctx.setLineDash([2, 3]);
      ctx.beginPath(); ctx.moveTo(this.hoverX, top); ctx.lineTo(this.hoverX, bottom); ctx.stroke();
      ctx.restore();
    }
  }

  private showAtPointer(event: PointerEvent): void {
    if (!this.samples.length) return;
    const rect = this.canvas.getBoundingClientRect();
    const localX = event.clientX - rect.left;
    const left = PAD.left;
    const right = Math.max(left + 1, rect.width - PAD.right);
    const duration = Math.max(600, this.samples.at(-1)?.duration_s ?? 3600);
    const targetTime = Math.max(0, Math.min(1, (localX - left) / (right - left))) * duration;
    let nearest = this.samples[0];
    for (const sample of this.samples) {
      if (Math.abs(sample.t - targetTime) < Math.abs(nearest.t - targetTime)) nearest = sample;
    }
    this.hoverX = Math.max(left, Math.min(right, localX));
    this.showSample(nearest, localX, event.clientY - rect.top);
    this.draw();
  }

  private showSample(sample: TimelineSample, localX: number, localY: number): void {
    this.tooltip.replaceChildren();
    const time = document.createElement("strong");
    time.textContent = formatSimTime(sample.t);
    const trueValue = document.createElement("span");
    trueValue.textContent = `True  ${sample.trueTempC.toFixed(1)} °C`;
    const reported = document.createElement("span");
    reported.textContent = `Reported  ${sample.reportedTempC.toFixed(1)} °C`;
    const model = document.createElement("span");
    model.textContent = `Model  ${sample.modelTempC.toFixed(1)} °C`;
    this.tooltip.append(time, trueValue, document.createElement("br"), reported, document.createElement("br"), model);
    this.tooltip.hidden = false;
    const maxLeft = Math.max(0, this.width - 170);
    this.tooltip.style.left = `${Math.max(4, Math.min(maxLeft, localX + this.canvas.offsetLeft + 10))}px`;
    this.tooltip.style.top = `${Math.max(3, Math.min(this.height - 78, localY + this.canvas.offsetTop - 24))}px`;
  }

  disconnect(): void { this.observer.disconnect(); }
}
