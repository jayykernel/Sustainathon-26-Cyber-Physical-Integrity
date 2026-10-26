import type { Classification } from "../sim/classifier";

export function formatSimTime(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const remainder = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

export function classificationLabel(classification: Classification): string {
  if (classification === "confirmed") return "Confirmed";
  if (classification === "suspect") return "Suspect";
  return "Safe";
}

export function signed(value: number, digits = 1): string {
  const rounded = value.toFixed(digits);
  return value >= 0 ? `+${rounded}` : rounded;
}

export function percent(fraction: number): number {
  return Math.round(Math.min(1, Math.max(0, fraction)) * 100);
}
