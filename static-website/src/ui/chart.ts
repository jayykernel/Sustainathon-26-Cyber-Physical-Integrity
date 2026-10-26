import type { TimelineSample } from "../sim/timeline";
import { COLORS } from "../tokens";
import { classificationLabel, formatSimTime } from "./format";

const PAD = { left: 27, right: 10, top: 14, bottom: 16 };
const FONT = '9px "IBM Plex Sans", "Segoe UI", system-ui, sans-serif';

/** Live strip chart for samples received from the backend WebSocket. */
export class TemperatureChart {
  private readonly ctx: CanvasRenderingContext2D;
  private readonly samples: TimelineSample[] = [];
  private readonly observer: ResizeObserver;
  private width = 0;
  private height = 0;

  constructor(private readonly canvas: HTMLCanvasElement) {
    const context = canvas.getContext("2d");
    if (!context) throw new Error("The temperature chart could not get a 2D context");
    this.ctx = context;
    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(canvas);
    this.resize();
    this.draw();
  }

  reset(): void {
    this.samples.length = 0;
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
    ctx.strokeStyle = COLORS.hazard;
    ctx.setLineDash([4, 3]);
    ctx.beginPath(); ctx.moveTo(left, y(55)); ctx.lineTo(right, y(55)); ctx.stroke();
    ctx.setLineDash([]);
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
    if (this.samples.some((sample) => sample.attackActive)) {
      const onset = this.samples.find((sample) => sample.attackActive)?.t ?? 0;
      ctx.fillStyle = "rgba(194, 58, 34, 0.07)";
      ctx.fillRect(x(onset), top, Math.max(1, right - x(onset)), plotHeight);
    }

    ctx.save(); ctx.beginPath(); ctx.rect(left, top, plotWidth, plotHeight); ctx.clip();
    const line = (pick: (sample: TimelineSample) => number, color: string, width: number, dash: number[] = []) => {
      if (this.samples.length < 1) return;
      ctx.beginPath();
      this.samples.forEach((sample, index) => {
        const px = x(sample.t), py = y(pick(sample));
        if (index === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      });
      ctx.strokeStyle = color; ctx.lineWidth = width; ctx.setLineDash(dash); ctx.stroke(); ctx.setLineDash([]);
    };
    line((sample) => sample.reportedTempC, COLORS.hazard, 1.1, [3, 2]);
    line((sample) => sample.modelTempC, COLORS.protected, 1);
    line((sample) => sample.trueTempC, COLORS.nominal, 1.7);
    ctx.restore();

    const latest = this.samples.at(-1);
    if (latest) {
      ctx.strokeStyle = COLORS.ink; ctx.globalAlpha = 0.2;
      ctx.beginPath(); ctx.moveTo(x(latest.t), top); ctx.lineTo(x(latest.t), bottom); ctx.stroke();
      ctx.globalAlpha = 1;
      this.canvas.setAttribute("aria-label", `Live backend temperature at ${formatSimTime(latest.t)}. True ${latest.trueTempC.toFixed(1)} degrees Celsius. Reported ${latest.reportedTempC.toFixed(1)}. Model estimate ${latest.modelTempC.toFixed(1)}. Classifier ${classificationLabel(latest.classification)}.`);
    }
  }

  disconnect(): void { this.observer.disconnect(); }
}
