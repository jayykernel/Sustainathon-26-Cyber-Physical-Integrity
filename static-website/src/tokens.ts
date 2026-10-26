import type { Classification } from "./sim/classifier";

/**
 * Named colour tokens shared by the DOM interface and the 3D scene.
 *
 * These mirror `docs/DESIGN.md`. The page is a light measurement bench, so the
 * scene background and floor use the same bench and rule colours as the UI.
 */
export const COLORS = {
  bench: "#ECEFF1",
  benchDeep: "#E2E7EA",
  sheet: "#FBFCFC",
  rule: "#C9D1D6",
  ink: "#14232C",
  inkSoft: "#52636D",
  protected: "#1D5FA8",
  hazard: "#C23A22",
  caution: "#A86A12",
  nominal: "#1E7F5C",
  graphite: "#2B3A43",
  tire: "#1F2A30",
  glass: "#41545F",
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
    return mix(COLORS.nominal, COLORS.caution, fraction / 0.65);
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
