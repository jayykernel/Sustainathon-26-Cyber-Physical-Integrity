import { BATTERY, SIMULATION } from "../config";
import { stageIndexForSimTime } from "../stages";
import { AttackClassifier, type Classification, type ClassifierEvidence } from "./classifier";
import { Ekf } from "./ekf";
import { FakeDataInjector, type FakeTelemetry } from "./fakeData";
import { OneRcTwin, clamp } from "./twin";

export interface TimelineSample {
  /** Simulated seconds since the run started. */
  t: number;
  /** Owning narrative stage, 0-6. */
  stageIndex: number;
  /** Physical cell temperature in degrees Celsius. */
  trueTempC: number;
  /** Temperature reported by the (possibly spoofed) sensor. */
  reportedTempC: number;
  /** EKF posterior temperature estimate. */
  ekfTempC: number;
  /** Physical-model (one-RC) temperature prediction. */
  modelTempC: number;
  /** Physical terminal voltage in volts. */
  trueVoltageV: number;
  /** Voltage reported by the (possibly spoofed) sensor. */
  reportedVoltageV: number;
  /** True state of charge as a fraction. */
  soc: number;
  /** Current in amperes. Negative is discharge. */
  currentA: number;
  /** Normalised innovation squared. */
  nis: number;
  /** Temperature innovation in degrees Celsius. */
  tempResidual: number;
  /** EKF gain on the temperature channel. */
  temperatureGain: number;
  /** Classifier verdict at this sample. */
  classification: Classification;
  /** Rolling evidence behind the classifier verdict. */
  evidence: ClassifierEvidence;
  /** Whether the digital twin has been engaged. */
  twinActive: boolean;
  /** Twin cell temperature in degrees Celsius. */
  twinTempC: number;
  /** Twin state of charge as a fraction. */
  twinSoc: number;
  /** Number of fabricated packets sent so far. */
  fakePackets: number;
  /** Most recent fabricated packet, if any. */
  lastFake: FakeTelemetry | null;
  /** Whether the twin still answers the attacker. */
  twinResponding: boolean;
  /** Simulated vehicle speed in kilometres per hour. */
  speedKmh: number;
  /** Whether the red alarm state is active. */
  alarm: boolean;
}

export interface Timeline {
  samples: readonly TimelineSample[];
  totalDuration_s: number;
  sampleAt(simTime: number): TimelineSample;
}

function lerp(from: number, to: number, fraction: number): number {
  return from + (to - from) * fraction;
}

function smoothstep(value: number): number {
  const bounded = clamp(value, 0, 1);
  return bounded * bounded * (3 - 2 * bounded);
}

function pseudoNoise(seed: number, t: number): number {
  const value = Math.sin((t + seed) * 12.9898) * 43758.5453;
  return (value - Math.floor(value)) * 2 - 1;
}

/** Traction load in amperes (positive magnitude, applied as discharge). */
function loadAt(t: number): number {
  if (t < 120) return 30;
  if (t < 240) return lerp(30, 160, smoothstep((t - 120) / 120));
  if (t < 360) return lerp(160, 140, smoothstep((t - 240) / 120));
  if (t < 480) return 110;
  if (t < 600) return 70;
  if (t < SIMULATION.restAt_s) return 40;
  return 0;
}

/** Attack intensity ramps from the hijack stage to the detection stage. */
function intensityAt(t: number): number {
  if (t < 120) return 0;
  if (t < 240) return lerp(0, 0.45, smoothstep((t - 120) / 120));
  if (t < 360) return lerp(0.45, 0.85, smoothstep((t - 240) / 120));
  if (t < 420) return lerp(0.85, 1, smoothstep((t - 360) / 60));
  return 1;
}

/** Sensor spoof: a slow drift plus two oscillations the filter cannot track. */
function spoofBias(t: number): number {
  const intensity = intensityAt(t);
  const drift = 0.006 * Math.min(200, Math.max(0, t - 120));
  const oscillation = 1.6 + 0.7 * Math.sin(0.5 * t) + 0.3 * Math.sin(2.3 * t);
  return intensity * (oscillation + drift);
}

function speedAt(t: number): number {
  if (t < 120) return 72;
  if (t < 240) return lerp(72, 96, smoothstep((t - 120) / 120));
  if (t < 360) return lerp(96, 38, smoothstep((t - 240) / 120));
  if (t < 480) return lerp(38, 26, smoothstep((t - 360) / 120));
  if (t < 600) return lerp(26, 12, smoothstep((t - 480) / 120));
  if (t < SIMULATION.restAt_s) return lerp(12, 4, smoothstep((t - 600) / 60));
  return Math.max(0, 4 * (1 - (t - SIMULATION.restAt_s) / 15));
}

/**
 * Build the deterministic attack timeline once, then let scroll position pick
 * the sample to display. Precomputing guarantees that the narrative, the chart,
 * and the classifier always agree no matter how fast the page is scrolled.
 */
export function buildTimeline(): Timeline {
  const plant = new OneRcTwin();
  const shadowTwin = new OneRcTwin();
  const ekf = new Ekf();
  const classifier = new AttackClassifier();
  const fakeData = new FakeDataInjector();
  let activeTwin: OneRcTwin | null = null;
  let twinActive = false;
  let lastFake: FakeTelemetry | null = null;
  const samples: TimelineSample[] = [];

  for (let t = 0; t <= SIMULATION.totalDuration_s; t += 1) {
    const currentA = -loadAt(t);
    const plantOutput = plant.step(currentA);
    const shadowOutput = shadowTwin.step(currentA);
    const intensity = intensityAt(t);

    const trueTempC = plantOutput.tempC;
    const trueVoltageV = plantOutput.voltageV;
    const reportedTempC = trueTempC + spoofBias(t) + pseudoNoise(9.3, t) * 0.03;
    const reportedVoltageV =
      trueVoltageV + intensity * 0.02 * Math.sin(1.7 * t) + pseudoNoise(1.7, t) * 0.002;

    if (!ekf.isInitialized) ekf.initialize(reportedVoltageV, reportedTempC);
    else ekf.predict(currentA);
    const update = ekf.update(reportedVoltageV, reportedTempC, currentA);
    // The independent physical prediction is the reference for a sensor spoof.
    // The EKF state can slowly absorb a biased channel; the model cannot.
    const modelTempC = shadowOutput.tempC;
    const tempResidual = reportedTempC - modelTempC;
    const classification = classifier.update({
      nis: update.nis,
      tempResidual,
    });

    if (!twinActive && classification === "confirmed") {
      twinActive = true;
      // Seed the twin from the filter's SOC estimate and the physical model's
      // fast states. The twin is then stepped with the commanded current.
      activeTwin = new OneRcTwin({
        soc: update.state.soc,
        v1: shadowOutput.state.v1,
        tempC: shadowOutput.tempC,
      });
    }

    const twinOutput = activeTwin ? activeTwin.step(currentA) : null;

    if (
      twinActive &&
      t >= 600 &&
      t < SIMULATION.restAt_s &&
      t % SIMULATION.fakePacketInterval_s === 0
    ) {
      lastFake = fakeData.request(t);
    }
    if (t >= SIMULATION.restAt_s) fakeData.stopResponding();

    samples.push({
      t,
      stageIndex: stageIndexForSimTime(t),
      trueTempC,
      reportedTempC,
      ekfTempC: update.tempC,
      modelTempC,
      trueVoltageV,
      reportedVoltageV,
      soc: plantOutput.state.soc,
      currentA,
      nis: update.nis,
      tempResidual,
      temperatureGain: update.temperatureGain,
      classification,
      evidence: classifier.evidence,
      twinActive,
      twinTempC: twinOutput?.tempC ?? shadowOutput.tempC,
      twinSoc: twinOutput?.state.soc ?? shadowOutput.state.soc,
      fakePackets: fakeData.packetCount,
      lastFake,
      twinResponding: twinActive && fakeData.isResponding,
      speedKmh: speedAt(t),
      // Internal alarms follow the EKF verdict, not the reported temperature:
      // the spoofed channel is exactly what the vehicle cannot trust. Alarms
      // clear when the vehicle enters rest mode.
      alarm: classification !== "safe" && t < SIMULATION.restAt_s,
    });
  }

  return {
    samples,
    totalDuration_s: SIMULATION.totalDuration_s,
    sampleAt(simTime: number): TimelineSample {
      const index = Math.round(clamp(simTime, 0, SIMULATION.totalDuration_s));
      return samples[index];
    },
  };
}

/** Initial pack temperature is used by the HUD before the first sample. */
export const INITIAL_TEMP_C = BATTERY.T_amb_C;
