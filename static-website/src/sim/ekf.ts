import { BATTERY, SENSORS } from "../config";
import type { TwinState } from "./twin";
import { ocvFromSoc, socFromOcv } from "./twin";
import {
  addMatrix,
  allFinite,
  diagonal,
  identity,
  invert2,
  matrixVector,
  multiply,
  quadraticForm,
  subtractMatrix,
  symmetrize,
  transpose,
  type Matrix,
} from "./linalg";

export interface EkfUpdate {
  /** Normalised innovation squared for the voltage and temperature pair. */
  nis: number;
  /** Measurement-minus-prediction vector [voltage, temperature]. */
  innovation: [number, number];
  /** Standard deviation of each innovation channel. */
  innovationStd: [number, number];
  /** Posterior state estimate. */
  state: TwinState;
  /** Estimated terminal voltage in volts. */
  voltageV: number;
  /** Estimated cell temperature in degrees Celsius. */
  tempC: number;
  /** Kalman gain applied to the temperature channel, for diagnostics. */
  temperatureGain: number;
}

const STATE_DIMENSION = 3;

/**
 * Extended Kalman filter for the one-RC battery state [SOC, V1, T].
 *
 * The filter is given the commanded current and measured voltage/temperature.
 * A manipulated temperature channel produces a persistent innovation, which is
 * the signal the attack classifier uses.
 */
export class Ekf {
  private x: [number, number, number] = [0, 0, 0];
  private P: Matrix = diagonal([0.25 ** 2, 0.1 ** 2, 2 ** 2]);
  private initialized = false;
  // The thermal model is trusted more than the temperature sensor: a spoofed
  // measurement must show up as a persistent innovation instead of being
  // absorbed into the state estimate.
  private readonly Q: Matrix = diagonal([1e-6, 1e-5, 1e-4]);
  private readonly R: Matrix = diagonal([SENSORS.V_sigma_V ** 2, SENSORS.T_sigma_C ** 2]);

  get isInitialized(): boolean {
    return this.initialized;
  }

  get estimatedState(): TwinState {
    return { soc: this.x[0], v1: this.x[1], tempC: this.x[2] };
  }

  initialize(voltageV: number, tempC: number): void {
    this.x = [socFromOcv(voltageV), 0, tempC];
    this.P = diagonal([0.25 ** 2, 0.1 ** 2, 2 ** 2]);
    this.initialized = true;
  }

  reset(): void {
    this.x = [0, 0, 0];
    this.P = diagonal([0.25 ** 2, 0.1 ** 2, 2 ** 2]);
    this.initialized = false;
  }

  /** Advance the state estimate and covariance by one time step. */
  predict(currentA: number, ambientC: number = BATTERY.T_amb_C, dt_s: number = 1): TwinState {
    if (!this.initialized) throw new Error("EKF is not initialized");
    const [soc, v1, tempC] = this.x;
    const decay = Math.exp(-dt_s / BATTERY.tau1_s);
    const nextSoc = soc + (BATTERY.eta * currentA * dt_s) / (3600 * BATTERY.Q_Ah);
    const nextV1 = v1 * decay + BATTERY.R1_ohm * (1 - decay) * currentA;
    const heatW = currentA * currentA * (BATTERY.R0_ohm + BATTERY.R1_ohm);
    const nextTemp =
      tempC +
      (dt_s / BATTERY.C_th_J_per_K) *
        (heatW - (tempC - ambientC) / BATTERY.R_th_K_per_W);

    this.x = [nextSoc, nextV1, nextTemp];
    const transition = diagonal([1, decay, 1 - dt_s / (BATTERY.C_th_J_per_K * BATTERY.R_th_K_per_W)]);
    this.P = symmetrize(addMatrix(multiply(multiply(transition, this.P), transpose(transition)), this.Q));
    return this.estimatedState;
  }

  /** Apply a voltage/temperature measurement and return innovation diagnostics. */
  update(voltageV: number, tempC: number, currentA: number): EkfUpdate {
    if (!this.initialized) throw new Error("EKF is not initialized");
    const [soc, v1, estimateTemp] = this.x;
    const predictedVoltage = ocvFromSoc(soc) + currentA * BATTERY.R0_ohm + v1;
    const innovation: [number, number] = [voltageV - predictedVoltage, tempC - estimateTemp];
    const H: Matrix = [
      [this.ocvSlope(soc), 1, 0],
      [0, 0, 1],
    ];

    const Ht = transpose(H);
    const S = addMatrix(multiply(multiply(H, this.P), Ht), this.R);
    const SInverse = invert2(S);
    const gain = multiply(multiply(this.P, Ht), SInverse);

    const updateVector = matrixVector(gain, innovation);
    this.x = [
      this.x[0] + updateVector[0],
      this.x[1] + updateVector[1],
      this.x[2] + updateVector[2],
    ];

    const identityMatrix = identity(STATE_DIMENSION);
    const residualMap = subtractMatrix(identityMatrix, multiply(gain, H));
    this.P = symmetrize(
      addMatrix(
        multiply(multiply(residualMap, this.P), transpose(residualMap)),
        multiply(multiply(gain, this.R), transpose(gain)),
      ),
    );

    if (!allFinite(this.P) || !this.x.every(Number.isFinite)) {
      throw new Error("EKF produced a non-finite state or covariance");
    }

    const nis = quadraticForm(innovation, SInverse);
    return {
      nis,
      innovation,
      innovationStd: [Math.sqrt(S[0][0]), Math.sqrt(S[1][1])],
      state: this.estimatedState,
      voltageV: predictedVoltage,
      tempC: this.x[2],
      temperatureGain: gain[2][1],
    };
  }

  /** Evaluate a measurement without mutating the filter. Used by diagnostics. */
  computeNIS(voltageV: number, tempC: number, currentA: number): number {
    const savedX: [number, number, number] = [...this.x];
    const savedP = this.P.map((row) => [...row]);
    const savedInitialized = this.initialized;
    try {
      if (!this.initialized) this.initialize(voltageV, tempC);
      this.predict(currentA);
      return this.update(voltageV, tempC, currentA).nis;
    } finally {
      this.x = savedX;
      this.P = savedP;
      this.initialized = savedInitialized;
    }
  }

  private ocvSlope(soc: number): number {
    const delta = 0.01;
    const lower = Math.max(0, soc - delta);
    const upper = Math.min(1, soc + delta);
    if (upper === lower) return 0;
    return (ocvFromSoc(upper) - ocvFromSoc(lower)) / (upper - lower);
  }
}
