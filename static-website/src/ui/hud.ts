import type { Classification } from "../sim/classifier";
import type { TimelineSample } from "../sim/timeline";
import { classificationLabel, formatSimTime, percent, signed } from "./format";
import type { TemperatureChart } from "./chart";

function requireElement<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Missing required element #${id}`);
  return element as T;
}

function chipClass(classification: Classification): string {
  return `chip--${classification === "confirmed" ? "confirmed" : classification === "suspect" ? "suspect" : "nominal"}`;
}

/** Binds the deterministic sample to the DOM readouts. */
export class Hud {
  private readonly clock = requireElement("clock");
  private readonly speed = requireElement("speed");
  private readonly stateChip = requireElement("state-chip");
  private readonly channel = requireElement("channel");
  private readonly classification = requireElement("classification");
  private readonly windowNote = requireElement("window-note");
  private readonly residualFlag = requireElement("residual-flag");
  private readonly trueTemp = requireElement("true-temp");
  private readonly reportedTemp = requireElement("reported-temp");
  private readonly modelTemp = requireElement("model-temp");
  private readonly residual = requireElement("residual");
  private readonly nis = requireElement("nis");
  private readonly soc = requireElement("soc");
  private readonly evidenceFill = requireElement("evidence-fill");
  private readonly evidenceValue = requireElement("evidence-value");
  private readonly chartTime = requireElement("chart-time");
  private readonly twinPanel = requireElement("twin-panel");
  private readonly twinState = requireElement("twin-state");
  private readonly twinTemp = requireElement("twin-temp");
  private readonly twinSoc = requireElement("twin-soc");
  private readonly fakePackets = requireElement("fake-packets");
  private readonly twinUplink = requireElement("twin-uplink");
  private lastT = -1;

  constructor(private readonly chart: TemperatureChart) {}

  update(sample: TimelineSample): void {
    this.chart.render(sample);
    if (sample.t === this.lastT) return;
    this.lastT = sample.t;

    this.clock.textContent = formatSimTime(sample.t);
    this.speed.textContent = `${sample.currentA.toFixed(1)} A`;
    this.channel.textContent = this.channelFor(sample);

    this.setChip(this.stateChip, sample.classification);
    this.setChip(this.classification, sample.classification);

    this.windowNote.textContent = sample.attackActive ? "backend attack signal active" : "backend telemetry stream";
    this.residualFlag.textContent =
      sample.classification === "confirmed"
        ? "strong residual in window"
        : sample.classification === "suspect"
          ? "residual outside tolerance"
          : "no persistent residual";

    this.trueTemp.textContent = `${sample.trueTempC.toFixed(1)} °C`;
    this.reportedTemp.textContent = `${sample.reportedTempC.toFixed(1)} °C`;
    this.modelTemp.textContent = `${sample.modelTempC.toFixed(1)} °C`;
    this.residual.textContent = `${signed(sample.tempResidual)} °C`;
    this.nis.textContent = sample.nis.toFixed(1);
    this.soc.textContent = `${(sample.soc * 100).toFixed(1)} %`;

    const evidence = percent(sample.evidence.strongResidualFraction);
    this.evidenceFill.style.width = `${evidence}%`;
    this.evidenceFill.style.backgroundColor =
      sample.classification === "confirmed" ? "#C23A22" : "#A86A12";
    this.evidenceValue.textContent = `${evidence} %`;

    this.chartTime.textContent = `${formatSimTime(sample.t)} / ${formatSimTime(sample.duration_s ?? 3600)}`;

    this.twinPanel.dataset.engaged = String(sample.twinActive);
    if (sample.twinActive) {
      this.twinState.textContent = sample.twinResponding ? "Safe mode" : "Confirmed";
      this.twinTemp.textContent = `${sample.twinTempC.toFixed(1)} °C`;
      this.twinSoc.textContent = `${(sample.twinSoc * 100).toFixed(1)} %`;
      this.fakePackets.textContent = sample.twinResponding ? "Guard active" : "Monitoring";
      this.twinUplink.textContent = sample.controlMode ?? "Normal";
    } else {
      this.twinState.textContent = "Not engaged";
      this.twinTemp.textContent = "—";
      this.twinSoc.textContent = "—";
      this.fakePackets.textContent = "Monitoring";
      this.twinUplink.textContent = sample.controlMode ?? "Normal";
    }
  }

  reset(): void { this.lastT = -1; this.chart.reset(); }

  private setChip(element: HTMLElement, classification: Classification): void {
    element.classList.remove("chip--nominal", "chip--suspect", "chip--confirmed");
    element.classList.add(chipClass(classification));
    element.textContent = classificationLabel(classification);
  }

  private channelFor(sample: TimelineSample): string {
    return sample.channel ?? (sample.attackActive ? "Under investigation" : "Nominal");
  }
}
