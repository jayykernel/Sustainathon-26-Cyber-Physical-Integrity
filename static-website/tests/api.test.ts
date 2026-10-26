import { describe, expect, it } from "vitest";
import { toTimelineSample, type BackendFrame } from "../src/api";

function frame(state: string): BackendFrame {
  return {
    t: 1800,
    truth: { temp: 42, v: 3.8, i: 60, soc: 0.7 },
    truth_undefended: { temp: 49 },
    reported: { temp: 46, v: 3.9, i: 60 },
    predicted: { temp: 43, v: 3.8, soc: 0.69 },
    residual: { temp: 3 },
    evidence: {
      nis: 14, nis_thr: 11,
      cusum: { temp: 4, v: 0, i: 0 },
      cusum_thr: 3,
      probe: { active: true, gain_v: 0.9, gain_i: 1, gain_min: 0.7, failed: false },
    },
    state,
    localization: { channel: "temperature", confidence: 0.9 },
    control: { i_req: 80, i_cmd: 60, i_safe: 60, mode: state === "SAFE_MODE" ? "derated" : "normal" },
    margins: { temp: 13, v: 0.3 },
    attack: { active: true, name: "Model synthesis", onset: 120 },
  };
}

describe("backend frame adapter", () => {
  it("maps backend telemetry and classifier states into the scene model", () => {
    const sample = toTimelineSample(frame("SAFE_MODE"), 3600);
    expect(sample.trueTempC).toBe(42);
    expect(sample.reportedTempC).toBe(46);
    expect(sample.modelTempC).toBe(43);
    expect(sample.currentA).toBe(60);
    expect(sample.classification).toBe("confirmed");
    expect(sample.twinActive).toBe(true);
    expect(sample.attackActive).toBe(true);
    expect(sample.stageIndex).toBe(3);
    expect(sample.controlMode).toBe("derated");
  });

  it("does not invent an alert for a normal backend frame", () => {
    const input = frame("NORMAL");
    input.attack.active = false;
    const sample = toTimelineSample(input, 3600);
    expect(sample.classification).toBe("safe");
    expect(sample.alarm).toBe(false);
    expect(sample.twinActive).toBe(false);
  });
});
