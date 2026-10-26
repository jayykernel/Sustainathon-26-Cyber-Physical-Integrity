import { SIMULATION } from "../config";
import { clamp, ocvFromSoc } from "./twin";

export interface FakeTelemetry {
  /** Simulated seconds since the run started. */
  timestamp_s: number;
  /** Fabricated cell temperature in degrees Celsius. */
  tempC: number;
  /** Fabricated state of charge as a fraction. */
  soc: number;
  /** Fabricated terminal voltage in volts. */
  voltageV: number;
}

function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Generates a bounded number of plausible but fabricated telemetry packets.
 *
 * The attack story needs the twin to answer the attacker with a healthy-looking
 * pack, then fall silent. The generator is seeded so the timeline is
 * reproducible.
 */
export class FakeDataInjector {
  private readonly random: () => number;
  private sent = 0;
  private responding = true;

  constructor(
    private readonly maxPackets: number = SIMULATION.maxFakePackets,
    seed = 0x5eed1234,
  ) {
    this.random = mulberry32(seed);
  }

  get packetCount(): number {
    return this.sent;
  }

  get isResponding(): boolean {
    return this.responding && this.sent < this.maxPackets;
  }

  request(timestamp_s: number): FakeTelemetry | null {
    if (!this.isResponding) return null;

    const noise = this.random();
    const tempC = clamp(29 + noise * 3.5 + 0.4 * Math.sin(timestamp_s * 0.05), 25, 38);
    const soc = clamp(0.82 + (this.random() - 0.5) * 0.08, 0.7, 0.95);
    const voltageV = ocvFromSoc(soc) + (this.random() - 0.5) * 0.02;
    this.sent += 1;
    return { timestamp_s, tempC, soc, voltageV };
  }

  stopResponding(): void {
    this.responding = false;
  }

  reset(): void {
    this.sent = 0;
    this.responding = true;
  }
}
