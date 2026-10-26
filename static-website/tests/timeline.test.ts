import { describe, expect, it } from "vitest";
import { SIMULATION } from "../src/config";
import { buildTimeline } from "../src/sim/timeline";

const timeline = buildTimeline();

describe("attack timeline", () => {
  it("starts safe and ends confirmed and stopped", () => {
    const first = timeline.sampleAt(0);
    const last = timeline.sampleAt(SIMULATION.totalDuration_s);
    expect(first.classification).toBe("safe");
    expect(last.classification).toBe("confirmed");
    expect(last.stageIndex).toBe(6);
    expect(last.speedKmh).toBe(0);
    expect(last.alarm).toBe(false);
  });

  it("moves safe to suspect to confirmed in order", () => {
    const firstSuspect = timeline.samples.findIndex((sample) => sample.classification === "suspect");
    const firstConfirmed = timeline.samples.findIndex(
      (sample) => sample.classification === "confirmed",
    );
    expect(firstSuspect).toBeGreaterThan(0);
    expect(firstConfirmed).toBeGreaterThan(firstSuspect);
    expect(timeline.samples[firstConfirmed].stageIndex).toBe(3);
    expect(firstConfirmed).toBeLessThan(480);
  });

  it("does not un-confirm a confirmed attack", () => {
    const firstConfirmed = timeline.samples.findIndex(
      (sample) => sample.classification === "confirmed",
    );
    const remainder = timeline.samples.slice(firstConfirmed);
    expect(remainder.every((sample) => sample.classification === "confirmed")).toBe(true);
  });

  it("never falls back to safe once suspicion has been raised", () => {
    const rank = { safe: 0, suspect: 1, confirmed: 2 } as const;
    const firstSuspect = timeline.samples.findIndex((sample) => sample.classification !== "safe");
    expect(firstSuspect).toBeGreaterThan(0);
    expect(
      timeline.samples
        .slice(firstSuspect)
        .every((sample) => rank[sample.classification] >= rank.suspect),
    ).toBe(true);
  });

  it("engages the twin only after confirmation", () => {
    const firstConfirmed = timeline.samples.findIndex(
      (sample) => sample.classification === "confirmed",
    );
    expect(timeline.samples.slice(0, firstConfirmed).every((sample) => !sample.twinActive)).toBe(
      true,
    );
    expect(timeline.samples[firstConfirmed].twinActive).toBe(true);
  });

  it("sends fabricated packets during deception and then goes silent", () => {
    const before = timeline.sampleAt(599);
    const during = timeline.sampleAt(620);
    const after = timeline.sampleAt(660);
    expect(before.fakePackets).toBe(0);
    expect(during.fakePackets).toBeGreaterThan(0);
    expect(during.twinResponding).toBe(true);
    expect(after.twinResponding).toBe(false);
    expect(after.fakePackets).toBe(SIMULATION.maxFakePackets);
  });

  it("raises alarms during the attack and clears them at rest", () => {
    expect(timeline.sampleAt(0).alarm).toBe(false);
    expect(timeline.sampleAt(300).alarm).toBe(true);
    expect(timeline.sampleAt(700).alarm).toBe(false);
  });

  it("advances through stages without going backwards", () => {
    const stages = timeline.samples.map((sample) => sample.stageIndex);
    expect(stages.every((stage, index) => index === 0 || stage >= stages[index - 1])).toBe(true);
    expect(stages[0]).toBe(0);
    expect(stages.at(-1)).toBe(6);
  });

  it("keeps the true pack below the hazard limit", () => {
    const peakTrue = Math.max(...timeline.samples.map((sample) => sample.trueTempC));
    const peakReported = Math.max(...timeline.samples.map((sample) => sample.reportedTempC));
    expect(peakTrue).toBeLessThan(55);
    expect(peakReported).toBeGreaterThan(52);
  });
});
