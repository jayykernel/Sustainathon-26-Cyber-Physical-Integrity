import { SIMULATION, STAGE_COUNT } from "./config";

export type StageId = "normal" | "hijack" | "alarm" | "ekf" | "twin" | "deception" | "rest";

export interface StageDefinition {
  id: StageId;
  index: number;
  /** Short label used in the stage rail and the live-region announcement. */
  label: string;
}

/**
 * Canonical stage order. The long-form copy lives next to each section in
 * `index.html` so the narrative and the page structure cannot drift apart.
 */
export const STAGES: readonly StageDefinition[] = [
  { id: "normal", index: 0, label: "Normal" },
  { id: "hijack", index: 1, label: "Hijack" },
  { id: "alarm", index: 2, label: "Alarms" },
  { id: "ekf", index: 3, label: "Detection" },
  { id: "twin", index: 4, label: "Digital twin" },
  { id: "deception", index: 5, label: "Deception" },
  { id: "rest", index: 6, label: "Rest mode" },
];

const cumulativeSeconds: number[] = [];
{
  let total = 0;
  for (const duration of SIMULATION.stageDurations_s) {
    cumulativeSeconds.push(total);
    total += duration;
  }
}

/** Map a continuous stage position in [0, 7] to simulated seconds. */
export function simTimeForStageFloat(stageFloat: number): number {
  const bounded = Math.min(STAGE_COUNT, Math.max(0, stageFloat));
  const index = Math.min(Math.floor(bounded), STAGE_COUNT - 1);
  const fraction = bounded - index;
  return cumulativeSeconds[index] + fraction * SIMULATION.stageDurations_s[index];
}

/** Stage index (0-6) that owns a simulated time. */
export function stageIndexForSimTime(simTime: number): number {
  const bounded = Math.max(0, Math.min(SIMULATION.totalDuration_s, simTime));
  let index = 0;
  while (index < STAGE_COUNT - 1 && bounded >= cumulativeSeconds[index + 1]) {
    index += 1;
  }
  return index;
}

/** Convert page scroll progress [0, 1] to a continuous stage position [0, 7]. */
export function stageFloatForProgress(progress: number): number {
  return Math.min(STAGE_COUNT, Math.max(0, progress) * STAGE_COUNT);
}
