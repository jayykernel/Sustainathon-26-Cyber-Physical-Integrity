import type { TimelineSample } from "./sim/timeline";

export interface Scenario {
  id: string;
  title: string;
  description: string;
  level: string;
  story_steps: string[];
}

export interface BackendFrame {
  t: number;
  truth: { temp: number; v: number; i: number; soc: number };
  truth_undefended: { temp: number };
  reported: { temp: number; v: number; i: number };
  predicted: { temp: number; v: number; soc: number };
  residual: { temp: number };
  evidence: {
    nis: number;
    nis_thr: number;
    cusum: { temp: number; v: number; i: number };
    cusum_thr: number;
    probe: { active: boolean; gain_v: number | null; gain_i: number | null; gain_min: number; failed: boolean };
  };
  state: string;
  localization: { channel: string; confidence: number };
  control: { i_req: number; i_cmd: number; i_safe: number; mode: string };
  margins: { temp: number; v: number };
  attack: { active: boolean; name: string; onset: number | null };
}

export interface BackendEvent {
  t: number;
  kind: string;
  severity: string;
  text: string;
}

export function toTimelineSample(frame: BackendFrame, duration_s: number): TimelineSample {
  const state = frame.state.toUpperCase();
  const classification = state === "SAFE_MODE" || state === "CONFIRMED"
    ? "confirmed"
    : state === "SUSPECT"
      ? "suspect"
      : "safe";
  const stageIndex = Math.min(6, Math.floor((frame.t / Math.max(1, duration_s)) * 7));
  const residual = frame.reported.temp - frame.predicted.temp;
  const alarm = classification !== "safe" || frame.attack.active;
  return {
    t: frame.t,
    stageIndex,
    trueTempC: frame.truth.temp,
    reportedTempC: frame.reported.temp,
    ekfTempC: frame.predicted.temp,
    modelTempC: frame.predicted.temp,
    trueVoltageV: frame.truth.v,
    reportedVoltageV: frame.reported.v,
    soc: frame.truth.soc,
    currentA: frame.truth.i,
    nis: frame.evidence.nis,
    tempResidual: residual,
    temperatureGain: 0,
    classification,
    evidence: {
      windowSize: 0,
      nisFraction: frame.evidence.nis > frame.evidence.nis_thr ? 1 : 0,
      residualFraction: Math.abs(residual) > 1 ? 1 : 0,
      strongResidualFraction: Math.abs(residual) > 2.2 ? 1 : 0,
    },
    twinActive: state === "CONFIRMED" || state === "SAFE_MODE",
    twinTempC: frame.predicted.temp,
    twinSoc: frame.predicted.soc,
    fakePackets: 0,
    lastFake: null,
    twinResponding: state === "SAFE_MODE",
    speedKmh: 0,
    alarm,
    attackActive: frame.attack.active,
    duration_s,
    channel: frame.localization.channel,
    controlMode: frame.control.mode,
  };
}

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: { message?: string } } | null;
    throw new Error(body?.error?.message ?? `Request failed (${response.status})`);
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

export const api = {
  health: () => json<{ status: string; config_hash: string }>("/api/health"),
  scenarios: () => json<Scenario[]>("/api/scenarios"),
  createSession: (scenario_id: string, seed: number, speed: number) =>
    json<{ session_id: string }>("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario_id, seed, speed }),
    }),
  deleteSession: (id: string) => json<void>(`/api/sessions/${id}`, { method: "DELETE" }),
  sessionStatus: (id: string) => json<{ total_steps: number; status: string }>(`/api/sessions/${id}`),
};
