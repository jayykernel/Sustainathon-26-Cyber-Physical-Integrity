import { describe, expect, it } from "vitest";
import { OneRcTwin, ocvFromSoc, socFromOcv } from "../src/sim/twin";

describe("one-RC battery model", () => {
  it("round-trips the open-circuit-voltage table", () => {
    for (const soc of [0, 0.25, 0.5, 0.72, 1]) {
      expect(socFromOcv(ocvFromSoc(soc))).toBeCloseTo(soc, 2);
    }
  });

  it("charges, heats, and reports a finite voltage", () => {
    const twin = new OneRcTwin({ soc: 0.5, tempC: 35 });
    const before = twin.currentState;
    const output = twin.step(60);
    expect(output.state.soc).toBeGreaterThan(before.soc);
    expect(output.tempC).toBeGreaterThan(before.tempC);
    expect(Number.isFinite(output.voltageV)).toBe(true);
    expect(output.state.soc).toBeGreaterThanOrEqual(0);
    expect(output.state.soc).toBeLessThanOrEqual(1);
  });

  it("discharges and heats under traction load", () => {
    const twin = new OneRcTwin({ soc: 0.8, tempC: 35 });
    const output = twin.step(-160);
    expect(output.state.soc).toBeLessThan(0.8);
    expect(output.tempC).toBeGreaterThan(35);
  });

  it("cools toward ambient with no current", () => {
    const twin = new OneRcTwin({ soc: 0.5, tempC: 50 });
    const output = twin.step(0);
    expect(output.tempC).toBeLessThan(50);
  });
});
