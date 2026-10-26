/**
 * Simulation parameters.
 *
 * The one-RC and EKF values mirror the validated defaults in
 * `configs/default.yaml` so the browser simulation tells the same physical
 * story as the backend prototype. Nothing here is measured at runtime; the
 * scenario is fully simulated and deterministic.
 */
export const BATTERY = {
  /** Nominal capacity in ampere-hours. */
  Q_Ah: 60,
  /** Ohmic resistance in ohms. */
  R0_ohm: 0.0012,
  /** First RC resistance in ohms. */
  R1_ohm: 0.001083371522,
  /** First RC time constant in seconds. */
  tau1_s: 55.23743011,
  /** Thermal capacitance in joules per kelvin. */
  C_th_J_per_K: 800,
  /** Thermal resistance in kelvin per watt. */
  R_th_K_per_W: 2.5,
  /** Ambient temperature in degrees Celsius. */
  T_amb_C: 35,
  /** Initial state of charge as a fraction. */
  SOC_0: 0.72,
  /** Coulombic efficiency. */
  eta: 0.995,
  /** Open-circuit voltage table from 0 % to 100 % state of charge. */
  OCV_V: [3.0, 3.3, 3.45, 3.55, 3.62, 3.68, 3.75, 3.82, 3.92, 4.05, 4.2],
} as const;

export const SENSORS = {
  V_sigma_V: 0.008,
  T_sigma_C: 0.1,
} as const;

export const LIMITS = {
  T_warn_C: 50,
  T_hazard_C: 55,
  V_max_V: 4.2,
  V_min_V: 3.0,
} as const;

export const DETECTION = {
  /** Chi-square 2-DoF gate at roughly 99.5 % confidence. */
  nisThreshold: 11,
  /** Number of samples in the evidence window. */
  window: 20,
  /** Fraction of the window that must exceed the gate to raise suspicion. */
  suspectFraction: 0.35,
  /** Lower fraction at which an existing suspicion is released (hysteresis). */
  suspectReleaseFraction: 0.2,
  /** Fraction of the window that must exceed the gate to confirm an attack. */
  confirmedFraction: 0.75,
  /** Absolute temperature innovation that counts as evidence, in degrees C. */
  residualThreshold_C: 1.0,
  /** Temperature residual against the physical model that confirms an attack, in degrees C. */
  confirmedResidual_C: 2.2,
  /** A confirmed attack stays confirmed for the rest of the run. */
  latchConfirmed: true,
} as const;

export const SIMULATION = {
  dt_s: 1,
  /** Seconds from the first sample to rest mode. */
  totalDuration_s: 720,
  /** Per-stage durations in seconds. Seven stages. */
  stageDurations_s: [120, 120, 120, 120, 120, 60, 60],
  /** Sensor samples are taken every simulated second. */
  fakePacketInterval_s: 5,
  maxFakePackets: 12,
  /** Simulated seconds at which rest mode begins and alarms clear. */
  restAt_s: 660,
} as const;

export const STAGE_COUNT = SIMULATION.stageDurations_s.length;
