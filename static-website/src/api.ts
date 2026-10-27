import type { TimelineSample } from "./sim/timeline";

export interface Scenario {
  id: string;
  title: string;
  description: string;
  level: string;
  story_steps: string[];
}

export interface RecordedRun {
  recorded_only: true;
  scenario_id: string;
  seed: number;
  config_hash: string;
  frames: BackendFrame[];
  events: Array<{ type: "event"; t: number; kind: string; severity: string; text: string }>;
}

export const OFFLINE_SCENARIOS: Scenario[] = [
  { id: "baseline", title: "Honest charging", description: "Attack-free CC/CV charging with seeded sensor noise and cell variation.", level: "baseline", story_steps: ["Establish the charging trajectory and its noise floor."] },
  { id: "spike", title: "Telemetry spikes", description: "Brief temperature and voltage telemetry glitches.", level: "A0", story_steps: ["Brief glitches test range checks and fast passive alarms."] },
  { id: "drift", title: "Slow temperature drift", description: "Reported temperature drifts down while the cell heats.", level: "A1", story_steps: ["Gradual telemetry drift challenges cumulative detection."] },
  { id: "replay", title: "Cooling fault with replay", description: "Old telemetry is replayed while cooling degrades.", level: "A1", story_steps: ["Replayed signals conceal cooling degradation."] },
  { id: "model_synthesis", title: "Model-aware synthesis", description: "A private twin forges plausible telemetry without probe knowledge.", level: "A1", story_steps: ["A model-aware attacker forges coherent telemetry without probe knowledge."] },
  { id: "malicious_command", title: "Malicious CV request", description: "A valid-looking request overrides the charging taper.", level: "A1", story_steps: ["A valid-looking request changes the upstream CV taper."] },
  { id: "oracle_limit", title: "Oracle attacker limit", description: "An oracle attacker knows true actuator current.", level: "A2", story_steps: ["An oracle attacker demonstrates a stated threat-model limitation."] },
];

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
    cmd_unsafe?: boolean;
    command_tampered?: boolean;
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

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function backendFrame(value: unknown): value is BackendFrame {
  if (!record(value)) return false;
  const nested = (key: string): Record<string, unknown> | null => record(value[key]) ? value[key] as Record<string, unknown> : null;
  const truth = nested("truth"), undefended = nested("truth_undefended"), reported = nested("reported");
  const predicted = nested("predicted"), evidence = nested("evidence"), control = nested("control");
  const margins = nested("margins"), attack = nested("attack"), localization = nested("localization");
  const cusum = evidence && record(evidence.cusum) ? evidence.cusum : null;
  const probe = evidence && record(evidence.probe) ? evidence.probe : null;
  return finite(value.t) && typeof value.state === "string"
    && !!truth && finite(truth.temp) && finite(truth.v) && finite(truth.i) && finite(truth.soc)
    && !!undefended && finite(undefended.temp)
    && !!reported && finite(reported.temp) && finite(reported.v) && finite(reported.i)
    && !!predicted && finite(predicted.temp) && finite(predicted.v) && finite(predicted.soc)
    && !!evidence && finite(evidence.nis) && finite(evidence.nis_thr) && !!cusum
    && finite(cusum.temp) && finite(cusum.v) && finite(cusum.i) && finite(evidence.cusum_thr)
    && !!probe && typeof probe.active === "boolean" && typeof probe.failed === "boolean"
    && (probe.gain_v === null || finite(probe.gain_v)) && (probe.gain_i === null || finite(probe.gain_i))
    && (evidence.cmd_unsafe === undefined || typeof evidence.cmd_unsafe === "boolean")
    && (evidence.command_tampered === undefined || typeof evidence.command_tampered === "boolean")
    && !!control && finite(control.i_req) && finite(control.i_cmd) && finite(control.i_safe) && typeof control.mode === "string"
    && !!margins && finite(margins.temp) && finite(margins.v)
    && !!attack && typeof attack.active === "boolean" && typeof attack.name === "string"
    && (attack.onset === null || finite(attack.onset))
    && !!localization && typeof localization.channel === "string" && finite(localization.confidence);
}

export async function loadRecordedRun(scenarioId: string): Promise<RecordedRun> {
  const response = await fetch(`/demo-runs/${encodeURIComponent(scenarioId)}.json`);
  if (!response.ok) throw new Error(`No recorded run is available for ${scenarioId}.`);
  const payload: unknown = await response.json();
  if (!record(payload) || payload.recorded_only !== true || payload.scenario_id !== scenarioId
    || !finite(payload.seed) || typeof payload.config_hash !== "string"
    || !Array.isArray(payload.frames) || payload.frames.length === 0 || !payload.frames.every(backendFrame)) {
    throw new Error("The recorded run failed telemetry validation.");
  }
  const events = Array.isArray(payload.events) ? payload.events.flatMap((event) => {
    if (!record(event) || event.type !== "event" || !finite(event.t)
      || typeof event.kind !== "string" || typeof event.severity !== "string" || typeof event.text !== "string") return [];
    return [{ type: "event" as const, t: event.t, kind: event.kind, severity: event.severity, text: event.text }];
  }) : [];
  return {
    recorded_only: true,
    scenario_id: scenarioId,
    seed: payload.seed,
    config_hash: payload.config_hash,
    frames: payload.frames,
    events,
  };
}

/** Quiet scene state used until the first live backend frame arrives. */
export function createIdleSample(): TimelineSample {
  return {
    t: 0,
    stageIndex: 0,
    trueTempC: 35,
    reportedTempC: 35,
    ekfTempC: 35,
    modelTempC: 35,
    trueVoltageV: 3.7,
    reportedVoltageV: 3.7,
    soc: 0.72,
    currentA: 0,
    nis: 0,
    tempResidual: 0,
    temperatureGain: 0,
    classification: "safe",
    evidence: { windowSize: 0, nisFraction: 0, residualFraction: 0, strongResidualFraction: 0 },
    twinActive: false,
    twinProtecting: false,
    speedKmh: 0,
    alarm: false,
    attackActive: false,
    duration_s: 3600,
    channel: "Awaiting live run",
    controlMode: "Idle",
  };
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
    twinProtecting: state === "SAFE_MODE",
    speedKmh: 0,
    alarm,
    attackActive: frame.attack.active,
    duration_s,
    channel: frame.localization.channel,
    controlMode: frame.control.mode,
    backend: {
      undefendedTempC: frame.truth_undefended.temp,
      requestedCurrentA: frame.control.i_req,
      commandedCurrentA: frame.control.i_cmd,
      safeCurrentA: frame.control.i_safe,
      nisThreshold: frame.evidence.nis_thr,
      cusumTemp: frame.evidence.cusum.temp,
      cusumVoltage: frame.evidence.cusum.v,
      cusumCurrent: frame.evidence.cusum.i,
      cusumThreshold: frame.evidence.cusum_thr,
      probeActive: frame.evidence.probe.active,
      probeGainVoltage: frame.evidence.probe.gain_v,
      probeGainCurrent: frame.evidence.probe.gain_i,
      probeFailed: frame.evidence.probe.failed,
      commandGuardIntervened: frame.evidence.cmd_unsafe ?? false,
      commandTampered: frame.evidence.command_tampered ?? false,
      localizationConfidence: frame.localization.confidence,
      temperatureMarginC: frame.margins.temp,
      voltageMarginV: frame.margins.v,
      attackName: frame.attack.name,
      attackOnsetS: frame.attack.onset,
    },
  };
}

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: { message?: string }; detail?: { message?: string } } | null;
    throw new Error(body?.error?.message ?? body?.detail?.message ?? `Request failed (${response.status})`);
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

export const api = {
  health: () => json<{
    status: string;
    config_hash: string;
    thresholds_loaded: boolean;
    detection_error?: string;
  }>("/api/health"),
  scenarios: () => json<Scenario[]>("/api/scenarios"),
  benchmarks: () => json<{ results: unknown; meta: unknown }>("/api/benchmarks"),
  limits: () => json<unknown>("/api/limits"),
  createSession: (scenario_id: string, seed: number, speed: number) =>
    json<{ session_id: string }>("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario_id, seed, speed }),
    }),
  deleteSession: (id: string) => json<void>(`/api/sessions/${id}`, { method: "DELETE" }),
  sessionStatus: (id: string) => json<{ total_steps: number; status: string }>(`/api/sessions/${id}`),
  sendIncidentAlert: (alert: IncidentAlert) => json<{ received: boolean; duplicate: boolean }>("/api/incident-alerts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(alert),
  }),
};

export interface IncidentAlert {
  alert_id: string;
  created_at: string;
  vehicle_type: "car" | "two_wheeler";
  state: "suspect" | "confirmed";
  suspected_path: string;
  simulation_time_s: number;
  force: true;
}
