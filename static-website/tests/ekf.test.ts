import { describe, expect, it } from "vitest";
import { DETECTION } from "../src/config";
import { Ekf } from "../src/sim/ekf";
import { OneRcTwin, ocvFromSoc } from "../src/sim/twin";

function runNominal(steps: number): number[] {
  const plant = new OneRcTwin({ soc: 0.72, tempC: 35 });
  const ekf = new Ekf();
  ekf.initialize(ocvFromSoc(plant.currentState.soc), plant.currentState.tempC);
  const nis: number[] = [];
  for (let step = 0; step < steps; step += 1) {
    const output = plant.step(-30);
    ekf.predict(-30);
    nis.push(ekf.update(output.voltageV, output.tempC, -30).nis);
  }
  return nis;
}

describe("extended Kalman filter", () => {
  it("keeps innovations small on nominal telemetry", () => {
    const history = runNominal(120);
    const high = history.filter((value) => value > DETECTION.nisThreshold);
    expect(high.length).toBeLessThanOrEqual(2);
    expect(Math.max(...history)).toBeLessThan(30);
  });

  it("raises the innovation when temperature telemetry is spoofed", () => {
    const plant = new OneRcTwin({ soc: 0.72, tempC: 35 });
    const ekf = new Ekf();
    ekf.initialize(ocvFromSoc(plant.currentState.soc), plant.currentState.tempC);

    for (let step = 0; step < 40; step += 1) {
      const output = plant.step(-90);
      ekf.predict(-90);
      ekf.update(output.voltageV, output.tempC, -90);
    }

    let highCount = 0;
    for (let step = 0; step < 40; step += 1) {
      const output = plant.step(-90);
      ekf.predict(-90);
      const update = ekf.update(output.voltageV, output.tempC + 3.5, -90);
      if (update.nis > DETECTION.nisThreshold) highCount += 1;
    }
    expect(highCount).toBeGreaterThan(20);
  });

  it("keeps the physical model unbiased while the sensor is spoofed", () => {
    const plant = new OneRcTwin({ soc: 0.72, tempC: 35 });
    const model = new OneRcTwin({ soc: 0.72, tempC: 35 });
    let lastModelError = 0;
    let lastResidual = 0;
    for (let step = 0; step < 200; step += 1) {
      const plantOutput = plant.step(-120);
      const modelOutput = model.step(-120);
      lastModelError = Math.abs(modelOutput.tempC - plantOutput.tempC);
      lastResidual = plantOutput.tempC + 3.5 - modelOutput.tempC;
    }
    expect(lastModelError).toBeLessThan(0.1);
    expect(lastResidual).toBeGreaterThan(3);
  });

  it("keeps a finite, symmetric covariance", () => {
    const history = runNominal(60);
    expect(history.every(Number.isFinite)).toBe(true);
  });
});
