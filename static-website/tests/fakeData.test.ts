import { describe, expect, it } from "vitest";
import { FakeDataInjector } from "../src/sim/fakeData";

describe("fake data injector", () => {
  it("returns plausible, fabricated telemetry and then falls silent", () => {
    const injector = new FakeDataInjector(3);
    const packets = [
      injector.request(600),
      injector.request(605),
      injector.request(610),
      injector.request(615),
    ];
    expect(packets[0]).not.toBeNull();
    expect(packets[1]).not.toBeNull();
    expect(packets[2]).not.toBeNull();
    expect(packets[3]).toBeNull();
    expect(injector.packetCount).toBe(3);
    expect(injector.isResponding).toBe(false);
  });

  it("fabricates a healthy-looking pack that differs from a hot true pack", () => {
    const injector = new FakeDataInjector(1);
    const packet = injector.request(600);
    expect(packet).not.toBeNull();
    if (!packet) return;
    expect(packet.tempC).toBeGreaterThanOrEqual(25);
    expect(packet.tempC).toBeLessThanOrEqual(38);
    expect(packet.soc).toBeGreaterThanOrEqual(0.7);
    expect(packet.soc).toBeLessThanOrEqual(0.95);
    expect(packet.voltageV).toBeGreaterThan(3);
    expect(packet.voltageV).toBeLessThan(4.3);
    expect(Math.abs(packet.tempC - 52)).toBeGreaterThan(5);
  });

  it("stops responding on demand", () => {
    const injector = new FakeDataInjector(12);
    expect(injector.request(600)).not.toBeNull();
    injector.stopResponding();
    expect(injector.isResponding).toBe(false);
    expect(injector.request(605)).toBeNull();
  });

  it("resets to a fresh channel", () => {
    const injector = new FakeDataInjector(1);
    injector.request(600);
    injector.stopResponding();
    injector.reset();
    expect(injector.packetCount).toBe(0);
    expect(injector.isResponding).toBe(true);
    expect(injector.request(600)).not.toBeNull();
  });
});
