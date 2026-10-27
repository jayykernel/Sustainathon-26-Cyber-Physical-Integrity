import type { Classification } from "./sim/classifier";

/** Read the shared CSS palette so the HUD and Three.js use one token source. */
function cssColor(name: string): string {
  if (typeof document === "undefined") return "";
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export const COLORS = {
  get bench() { return cssColor("--bg"); },
  get benchDeep() { return cssColor("--surface"); },
  get sheet() { return cssColor("--ink"); },
  get rule() { return cssColor("--border"); },
  get ink() { return cssColor("--ink"); },
  get inkSoft() { return cssColor("--ink-muted"); },
  get protected() { return cssColor("--accent"); },
  get hazard() { return cssColor("--attack"); },
  get caution() { return cssColor("--suspect"); },
  get nominal() { return cssColor("--safe"); },
  get graphite() { return cssColor("--vehicle"); },
  get tire() { return cssColor("--tire"); },
  get glass() { return cssColor("--border"); },
  get heatNeutral() { return cssColor("--surface"); },
} as const;

export function colorForClassification(classification: Classification): string {
  if (classification === "confirmed") return COLORS.hazard;
  if (classification === "suspect") return COLORS.caution;
  return COLORS.nominal;
}

/** Map a temperature in degrees Celsius to a physical-state colour. */
export function colorForTemperature(tempC: number): string {
  const from = 35;
  const to = 55;
  const fraction = Math.min(1, Math.max(0, (tempC - from) / (to - from)));
  if (fraction < 0.65) {
    return mix(COLORS.heatNeutral, COLORS.caution, fraction / 0.65);
  }
  return mix(COLORS.caution, COLORS.hazard, (fraction - 0.65) / 0.35);
}

function mix(from: string, to: string, fraction: number): string {
  const start = parseInt(from.slice(1), 16);
  const end = parseInt(to.slice(1), 16);
  const channel = (shift: number): number => {
    const a = (start >> shift) & 0xff;
    const b = (end >> shift) & 0xff;
    return Math.round(a + (b - a) * fraction);
  };
  return `#${[16, 8, 0].map((shift) => channel(shift).toString(16).padStart(2, "0")).join("")}`;
}
