import { SIMULATION } from "../config";
import type { Classification } from "../sim/classifier";
import type { Timeline, TimelineSample } from "../sim/timeline";
import { COLORS } from "../tokens";
import { classificationLabel, formatSimTime } from "./format";

interface StateSegment {
  start: number;
  end: number;
  classification: Classification;
}

const PAD = { left: 27, right: 10, top: 14, bottom: 16 };
const TEMP_MIN = 30;
const TEMP_MAX = 60;
const FONT = '"IBM Plex Sans", "Segoe UI", system-ui, sans-serif';

function segmentColor(classification: Classification): string {
  if (classification === "confirmed") return COLORS.hazard;
  if (classification === "suspect") return COLORS.caution;
  return COLORS.nominal;
}

/**
 * A strip-chart recorder for the three temperature traces. The full twelve
 * minutes are drawn on a fixed axis and the trace reveals with scroll, so the
 * attack onset, the residuals, and the classifier verdict share one time axis.
 */
export class TemperatureChart {
  private readonly ctx: CanvasRenderingContext2D;
  private readonly segments: StateSegment[] = [];
  private readonly samples: readonly TimelineSample[];
  private readonly observer: ResizeObserver;
  private width = 0;
  private height = 0;
  private lastSample: TimelineSample | null = null;
  private renderedT = -1;
  private renderedWidth = -1;
  private renderedHeight = -1;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    timeline: Timeline,
  ) {
    const context = canvas.getContext("2d");
    if (!context) throw new Error("The temperature chart could not get a 2D context");
    this.ctx = context;
    this.samples = timeline.samples;

    for (const sample of timeline.samples) {
      const last = this.segments[this.segments.length - 1];
      if (last && last.classification === sample.classification) {
        last.end = sample.t;
      } else {
        this.segments.push({
          start: sample.t,
          end: sample.t,
          classification: sample.classification,
        });
      }
    }

    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(canvas);
    this.resize();
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
    this.renderedWidth = -1;
    this.renderedHeight = -1;
    if (this.lastSample) this.render(this.lastSample);
  }

  render(sample: TimelineSample): void {
    this.lastSample = sample;
    if (this.width <= 0) this.resize();
    if (this.width <= 0) return;
    if (
      sample.t === this.renderedT &&
      this.width === this.renderedWidth &&
      this.height === this.renderedHeight
    ) {
      return;
    }
    this.renderedT = sample.t;
    this.renderedWidth = this.width;
    this.renderedHeight = this.height;

    const ctx = this.ctx;
    const plotLeft = PAD.left;
    const plotRight = this.width - PAD.right;
    const plotTop = PAD.top;
    const plotBottom = this.height - PAD.bottom;
    const plotWidth = Math.max(1, plotRight - plotLeft);
    const plotHeight = Math.max(1, plotBottom - plotTop);
    const x = (time: number): number => plotLeft + (time / SIMULATION.totalDuration_s) * plotWidth;
    const y = (temp: number): number =>
      plotBottom - ((temp - TEMP_MIN) / (TEMP_MAX - TEMP_MIN)) * plotHeight;

    ctx.clearRect(0, 0, this.width, this.height);
    ctx.lineCap = "butt";
    ctx.lineJoin = "round";

    // Attack window tint.
    const attackStart = 120;
    const attackEnd = 660;
    ctx.fillStyle = "rgba(194, 58, 34, 0.055)";
    ctx.fillRect(
      x(attackStart),
      plotTop,
      x(attackEnd) - x(attackStart),
      plotHeight,
    );

    // Vertical time grid.
    ctx.strokeStyle = COLORS.rule;
    ctx.globalAlpha = 0.55;
    ctx.lineWidth = 1;
    for (let minute = 0; minute <= 12; minute += 2) {
      const gridX = x(minute * 60);
      ctx.beginPath();
      ctx.moveTo(gridX, plotTop);
      ctx.lineTo(gridX, plotBottom);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // Horizontal temperature grid.
    ctx.globalAlpha = 0.65;
    for (const temp of [35, 40, 45]) {
      ctx.beginPath();
      ctx.moveTo(plotLeft, y(temp));
      ctx.lineTo(plotRight, y(temp));
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    ctx.font = `9px ${FONT}`;
    ctx.fillStyle = COLORS.inkSoft;
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (const temp of [35, 45, 55]) {
      ctx.fillText(`${temp}`, plotLeft - 5, y(temp));
    }

    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (let minute = 0; minute <= 12; minute += 2) {
      const label = minute === 0 ? "0" : minute === 12 ? "12:00" : `${minute}:00`;
      ctx.fillText(label, x(minute * 60), plotBottom + 4);
    }

    // Limits.
    ctx.setLineDash([4, 3]);
    ctx.strokeStyle = COLORS.caution;
    ctx.globalAlpha = 0.55;
    ctx.beginPath();
    ctx.moveTo(plotLeft, y(50));
    ctx.lineTo(plotRight, y(50));
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.strokeStyle = COLORS.hazard;
    ctx.globalAlpha = 0.45;
    ctx.beginPath();
    ctx.moveTo(plotLeft, y(55));
    ctx.lineTo(plotRight, y(55));
    ctx.stroke();
    ctx.globalAlpha = 1;

    // Classifier state ribbon.
    for (const segment of this.segments) {
      if (segment.start > sample.t) break;
      const segmentEnd = Math.min(segment.end, sample.t);
      ctx.fillStyle = segmentColor(segment.classification);
      ctx.fillRect(
        x(segment.start),
        3,
        Math.max(1, x(segmentEnd) - x(segment.start)),
        3,
      );
    }

    ctx.save();
    ctx.beginPath();
    ctx.rect(plotLeft, plotTop, plotWidth, plotHeight);
    ctx.clip();

    // Model tolerance band.
    const visible = Math.floor(sample.t);
    ctx.beginPath();
    for (let index = 0; index <= visible; index += 1) {
      const point = this.samples[index];
      const px = x(point.t);
      const py = y(point.modelTempC + 1.2);
      if (index === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    for (let index = visible; index >= 0; index -= 1) {
      const point = this.samples[index];
      ctx.lineTo(x(point.t), y(point.modelTempC - 1.2));
    }
    ctx.closePath();
    ctx.fillStyle = "rgba(29, 95, 168, 0.08)";
    ctx.fill();

    const drawLine = (
      value: (point: TimelineSample) => number,
      color: string,
      width: number,
      dash: number[],
    ): void => {
      ctx.beginPath();
      for (let index = 0; index <= visible; index += 1) {
        const point = this.samples[index];
        const px = x(point.t);
        const py = y(value(point));
        if (index === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.setLineDash(dash);
      ctx.stroke();
      ctx.setLineDash([]);
    };

    drawLine((point) => point.reportedTempC, COLORS.hazard, 1.15, [3, 2]);
    drawLine((point) => point.modelTempC, COLORS.protected, 1, []);
    drawLine((point) => point.trueTempC, COLORS.nominal, 1.7, []);
    ctx.restore();

    // Onset marker.
    if (sample.t >= attackStart) {
      ctx.strokeStyle = COLORS.caution;
      ctx.globalAlpha = 0.7;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x(attackStart), plotTop);
      ctx.lineTo(x(attackStart), plotBottom);
      ctx.stroke();
      ctx.fillStyle = COLORS.caution;
      ctx.beginPath();
      ctx.moveTo(x(attackStart), plotTop);
      ctx.lineTo(x(attackStart) + 4, plotTop + 5);
      ctx.lineTo(x(attackStart) - 4, plotTop + 5);
      ctx.closePath();
      ctx.fill();
      if (sample.t > attackStart + 70) {
        ctx.font = `8px ${FONT}`;
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        ctx.fillText("spoof on", x(attackStart) + 4, plotTop + 7);
      }
      ctx.globalAlpha = 1;
    }

    // Now line and end points.
    const nowX = x(sample.t);
    ctx.strokeStyle = COLORS.ink;
    ctx.globalAlpha = 0.16;
    ctx.beginPath();
    ctx.moveTo(nowX, plotTop);
    ctx.lineTo(nowX, plotBottom);
    ctx.stroke();
    ctx.globalAlpha = 1;

    const endPoints: Array<{ value: number; color: string }> = [
      { value: sample.trueTempC, color: COLORS.nominal },
      { value: sample.reportedTempC, color: COLORS.hazard },
    ];
    for (const point of endPoints) {
      const pointY = Math.min(plotBottom, Math.max(plotTop, y(point.value)));
      ctx.fillStyle = point.color;
      ctx.beginPath();
      ctx.arc(nowX, pointY, 2.2, 0, Math.PI * 2);
      ctx.fill();
    }

    this.canvas.setAttribute(
      "aria-label",
      `Cell temperature at ${formatSimTime(sample.t)}. True ${sample.trueTempC.toFixed(
        1,
      )} degrees Celsius. Reported ${sample.reportedTempC.toFixed(
        1,
      )}. One-RC model ${sample.modelTempC.toFixed(1)}. Classifier ${classificationLabel(
        sample.classification,
      )}.`,
    );
  }

  disconnect(): void {
    this.observer.disconnect();
  }
}
