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
  private readonly calloutTemp = requireElement("callout-temp");
  private readonly calloutSoc = requireElement("callout-soc");
  private readonly calloutRate = requireElement("callout-rate");
  private readonly reportedTemp = requireElement("reported-temp");
  private readonly modelTemp = requireElement("model-temp");
  private readonly residual = requireElement("residual");
  private readonly nis = requireElement("nis");
  private readonly soc = requireElement("soc");
  private readonly evidenceFill = requireElement("evidence-fill");
  private readonly evidenceValue = requireElement("evidence-value");
  private readonly evidenceMeter = requireElement("evidence-meter");
  private readonly chartTime = requireElement("chart-time");
  private readonly responseState = requireElement("response-state");
  private readonly responseDetail = requireElement("response-detail");
  private readonly responsePanel = requireElement("response-panel");
  private readonly undefendedTemp = requireElement("undefended-temp");
  private readonly voltagePair = requireElement("voltage-pair");
  private readonly currentTriple = requireElement("current-triple");
  private readonly marginPair = requireElement("margin-pair");
  private readonly nisThreshold = requireElement("nis-threshold");
  private readonly cusumValues = requireElement("cusum-values");
  private readonly probeValues = requireElement("probe-values");
  private readonly localizationValues = requireElement("localization-values");
  private readonly attackValues = requireElement("attack-values");
  private readonly responseSteps = Array.from(document.querySelectorAll<HTMLElement>("[data-response-step]"));
  private lastT = -1;

  constructor(private readonly chart: TemperatureChart) {}

  update(sample: TimelineSample): void {
    this.chart.render(sample);
    if (sample.t === this.lastT) return;
    this.lastT = sample.t;
    document.body.dataset.telemetry = "live";

    this.clock.textContent = formatSimTime(sample.t);
    this.speed.textContent = `${sample.currentA.toFixed(1)} A`;
    this.channel.textContent = this.channelFor(sample);

    this.setChip(this.stateChip, sample.classification);
    this.setChip(this.classification, sample.classification);

    this.windowNote.textContent = sample.attackActive ? "backend attack signal active" : "backend telemetry stream";
    this.residualFlag.textContent = `Backend response state: ${sample.classification}`;

    this.trueTemp.textContent = `${sample.trueTempC.toFixed(1)} °C`;
    this.calloutTemp.textContent = `${sample.trueTempC.toFixed(1)} °C`;
    this.calloutSoc.textContent = `${(sample.soc * 100).toFixed(1)} %`;
    this.calloutRate.textContent = `${sample.currentA.toFixed(1)} A`;
    this.reportedTemp.textContent = `${sample.reportedTempC.toFixed(1)} °C`;
    this.modelTemp.textContent = `${sample.modelTempC.toFixed(1)} °C`;
    const backend = sample.backend;
    if (backend) {
      const gain = (value: number | null): string => value === null ? "—" : value.toFixed(3);
      this.undefendedTemp.textContent = `${backend.undefendedTempC.toFixed(1)} °C`;
      this.voltagePair.textContent = `${sample.trueVoltageV.toFixed(3)} / ${sample.reportedVoltageV.toFixed(3)} V`;
      this.currentTriple.textContent = `${backend.requestedCurrentA.toFixed(1)} / ${backend.commandedCurrentA.toFixed(1)} / ${backend.safeCurrentA.toFixed(1)} A`;
      this.marginPair.textContent = `${backend.temperatureMarginC.toFixed(1)} °C / ${backend.voltageMarginV.toFixed(3)} V`;
      this.nisThreshold.textContent = `${sample.nis.toFixed(2)} / ${backend.nisThreshold.toFixed(2)}`;
      this.cusumValues.textContent = `${backend.cusumTemp.toFixed(2)} / ${backend.cusumVoltage.toFixed(2)} / ${backend.cusumCurrent.toFixed(2)} · limit ${backend.cusumThreshold.toFixed(2)}`;
      this.probeValues.textContent = `${backend.probeActive ? "Active" : "Inactive"} / ${gain(backend.probeGainVoltage)} / ${gain(backend.probeGainCurrent)}${backend.probeFailed ? " · failed" : ""}`;
      this.localizationValues.textContent = `${sample.channel ?? "Unknown"} / score ${backend.localizationConfidence.toFixed(2)}`;
      this.attackValues.textContent = `${backend.attackName || "None"} / ${backend.attackOnsetS === null ? "not activated" : formatSimTime(backend.attackOnsetS)}`;
    }
    this.residual.textContent = `${signed(sample.tempResidual)} °C`;
    this.nis.textContent = sample.nis.toFixed(1);
    this.soc.textContent = `${(sample.soc * 100).toFixed(1)} %`;

    const evidence = percent(sample.evidence.strongResidualFraction);
    this.evidenceFill.style.width = `${evidence}%`;
    this.evidenceValue.textContent = `${evidence} %`;
    this.evidenceMeter.setAttribute("aria-valuenow", String(evidence));

    this.chartTime.textContent = `${formatSimTime(sample.t)} / ${formatSimTime(sample.duration_s ?? 3600)}`;

    const responseStep = sample.classification === "safe"
      ? "monitoring"
      : sample.classification === "suspect"
        ? "suspect"
        : sample.twinProtecting
          ? "safe-mode"
          : sample.twinActive
            ? "isolate"
            : "suspect";
    const responseLabels: Record<string, string> = {
      monitoring: "Monitoring",
      suspect: "Suspect",
      isolate: "Isolate",
      "safe-mode": "SAFE_MODE: current limited",
    };
    this.responseState.textContent = responseLabels[responseStep];
    this.responsePanel.dataset.state = responseStep;
    for (const step of this.responseSteps) {
      const active = step.dataset.responseStep === responseStep;
      step.classList.toggle("is-active", active);
      if (active) step.setAttribute("aria-current", "step");
      else step.removeAttribute("aria-current");
    }
    this.responseDetail.textContent = sample.channel ?? (sample.attackActive ? "Channel under investigation" : "No suspect path identified");
  }

  reset(): void {
    this.lastT = -1;
    document.body.dataset.telemetry = "waiting";
    this.windowNote.textContent = "Waiting for run";
    this.residualFlag.textContent = "Waiting for telemetry";
    this.classification.textContent = "Waiting";
    this.stateChip.textContent = "Waiting";
    for (const field of [this.trueTemp, this.reportedTemp, this.modelTemp, this.residual]) field.textContent = "-- °C";
    this.nis.textContent = "--";
    this.soc.textContent = "-- %";
    this.evidenceFill.style.width = "0%";
    this.evidenceValue.textContent = "--";
    this.evidenceMeter.setAttribute("aria-valuenow", "0");
    this.calloutTemp.textContent = "-- °C";
    this.calloutSoc.textContent = "-- %";
    this.calloutRate.textContent = "-- A";
    for (const field of [this.undefendedTemp, this.voltagePair, this.currentTriple, this.marginPair, this.nisThreshold, this.cusumValues, this.probeValues, this.localizationValues, this.attackValues]) {
      field.textContent = "Awaiting frame";
    }
    this.chart.reset();
  }

  private setChip(element: HTMLElement, classification: Classification): void {
    element.classList.remove("chip--nominal", "chip--suspect", "chip--confirmed");
    element.classList.add(chipClass(classification));
    element.textContent = classificationLabel(classification);
  }

  private channelFor(sample: TimelineSample): string {
    return sample.channel ?? (sample.attackActive ? "Under investigation" : "Nominal");
  }
}
