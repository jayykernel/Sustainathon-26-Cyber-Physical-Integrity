import { api, type Scenario } from "../api";

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as JsonObject
    : null;
}

function rows(value: unknown): JsonObject[] {
  return Array.isArray(value) ? value.map(object).filter((item): item is JsonObject => item !== null) : [];
}

function number(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function requiredElement<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Missing required element #${id}`);
  return element as T;
}

const detectorNames = [
  ["B0", "Range checks"],
  ["B1", "EKF / NIS"],
  ["B2", "EKF + CUSUM"],
  ["B2_probe_present", "B2 with probe"],
  ["B3", "Full defense"],
] as const;

function makeCell(row: HTMLTableRowElement, value: string, label: string, heading = false): void {
  const cell = document.createElement(heading ? "th" : "td");
  if (heading) cell.scope = "row";
  else cell.dataset.label = label;
  cell.textContent = value;
  row.append(cell);
}

function benchmarkSummary(payload: unknown): { results: JsonObject; meta: JsonObject } | null {
  const root = object(payload);
  const results = object(root?.results);
  const meta = object(root?.meta);
  const details = object(results?.details);
  return results && meta && details ? { results, meta } : null;
}

function renderBenchmarks(payload: unknown): boolean {
  const state = requiredElement("benchmark-status");
  const body = requiredElement("benchmark-rows");
  const wrap = requiredElement("benchmark-table-wrap");
  const summary = benchmarkSummary(payload);
  body.replaceChildren();
  if (!summary) {
    wrap.hidden = true;
    state.textContent = "Benchmark artifact is unavailable or has an unsupported structure.";
    return false;
  }

  const details = object(summary.results.details);
  if (!details) return false;
  const baselineRows = rows(details.baseline);
  const attackRows = Object.entries(details)
    .filter(([name]) => name !== "baseline")
    .flatMap(([, value]) => rows(value));

  for (const [detectorKey, detectorLabel] of detectorNames) {
    let detected = 0;
    let eligible = 0;
    let hazard = 0;
    let preempted = 0;
    let attackRuns = 0;
    let delays = 0;
    let delayCount = 0;
    let falseAlarms = 0;
    let baselineHours = 0;

    for (const run of attackRows) {
      const detector = object(object(run.detectors)?.[detectorKey]);
      if (!detector) continue;
      attackRuns += 1;
      if (detector.preempted_before_activation === true) preempted += 1;
      if (detector.attack_activated !== true) continue;
      eligible += 1;
      if (detector.detected === true) {
        detected += 1;
        const delay = number(detector.delay_s);
        if (delay !== null) {
          delays += delay;
          delayCount += 1;
        }
      }
      if (detector.hazard_event === true) hazard += 1;
    }
    for (const run of baselineRows) {
      const detector = object(object(run.detectors)?.[detectorKey]);
      if (!detector) continue;
      falseAlarms += number(detector.false_alarm_episodes) ?? 0;
      baselineHours += number(detector.false_alarm_hours) ?? 0;
    }

    const row = document.createElement("tr");
    makeCell(row, detectorLabel, "Detector", true);
    makeCell(row, eligible ? `${detected} / ${eligible} · ${Math.round((detected / eligible) * 100)}%` : "Unavailable", "Attack detection");
    makeCell(row, delayCount ? `${(delays / delayCount).toFixed(1)} s · detected runs` : "No detected runs", "Mean delay");
    makeCell(row, attackRuns ? `${preempted} / ${attackRuns}` : "Unavailable", "Pre-empted before onset");
    makeCell(row, baselineHours > 0 ? (falseAlarms / baselineHours).toFixed(3) : "Unavailable", "Baseline false alarms / h");
    makeCell(row, eligible ? `${hazard} / ${eligible} · ${Math.round((hazard / eligible) * 100)}%` : "Unavailable", "Attack hazard rate");
    body.append(row);
  }

  const seeds = Array.isArray(summary.meta.seeds) ? summary.meta.seeds.map(number).filter((seed): seed is number => seed !== null) : [];
  const hash = text(summary.meta.config_hash) ?? text(summary.results.config_hash) ?? "not supplied";
  const seedText = seeds.length ? `seeds ${Math.min(...seeds)}–${Math.max(...seeds)} · ${seeds.length} runs` : "seed range not supplied";
  const generated = text(summary.meta.generated_at_utc);
  requiredElement("benchmark-meta").textContent = `Config ${hash} · ${seedText}${generated ? ` · generated ${generated}` : ""} · Reproduce with make eval.`;
  state.textContent = "Values are aggregated from the backend evaluation artifact.";
  wrap.hidden = false;
  return true;
}

function appendListItems(list: HTMLElement, entries: Array<[string, string]>): void {
  list.replaceChildren();
  for (const [label, value] of entries) {
    const item = document.createElement("li");
    const strong = document.createElement("strong");
    strong.textContent = label;
    item.append(strong, document.createTextNode(value));
    list.append(item);
  }
}

function renderLimits(payload: unknown): void {
  const root = object(payload);
  if (!root) {
    appendListItems(requiredElement("method-list"), [["Backend unavailable", " Method details could not be loaded."]]);
    appendListItems(requiredElement("limits-list"), [["Backend unavailable", " Threat-model limits could not be loaded."]]);
    return;
  }

  const method = object(root.method) ?? {};
  const methodLabels: Record<string, string> = {
    state_estimation: "State estimation",
    passive_detection: "Passive detection",
    active_detection: "Active verification",
    response: "Conservative response",
  };
  appendListItems(
    requiredElement("method-list"),
    Object.entries(method).map(([key, value]) => [methodLabels[key] ?? key, ` — ${text(value) ?? "Unavailable"}`]),
  );

  const threat = object(root.threat_model) ?? {};
  const threatEntries = Object.entries(threat).flatMap(([key, value]) => {
    const label = key === "attacker_out_of_scope" ? "Out of scope" : key.replaceAll("_", " ");
    if (Array.isArray(value)) return value.flatMap((entry) => {
      const description = text(entry);
      return description ? [[label, ` — ${description}`] as [string, string]] : [];
    });
    const description = text(value);
    return description ? [[label, ` — ${description}`] as [string, string]] : [];
  });
  const limitations = Array.isArray(root.limitations)
    ? root.limitations.flatMap((entry) => {
        const description = text(entry);
        return description ? [["Limitation", ` — ${description}`] as [string, string]] : [];
      })
    : [];
  appendListItems(requiredElement("limits-list"), [...threatEntries, ...limitations]);
}

export class ResearchView {
  constructor(scenarioSelect: HTMLSelectElement) {
    const title = requiredElement("selected-scenario-title");
    const description = requiredElement("selected-scenario-copy");
    let scenarios: Scenario[] = [];
    const updateScenario = () => {
      const selected = scenarios.find((scenario) => scenario.id === scenarioSelect.value);
      title.textContent = selected ? `${selected.title} · ${selected.level}` : "Scenario details unavailable";
      description.textContent = selected?.description ?? "The backend scenario catalog has not supplied a description.";
    };
    scenarioSelect.addEventListener("change", updateScenario);
    this.setScenarios = (items) => {
      scenarios = items;
      updateScenario();
    };
  }

  private setScenarios: (scenarios: Scenario[]) => void = () => {};

  updateScenarios(scenarios: Scenario[]): void {
    this.setScenarios(scenarios);
  }

  async load(): Promise<void> {
    const status = requiredElement("benchmark-status");
    const results = await Promise.allSettled([api.benchmarks(), api.limits()]);
    if (results[0].status === "fulfilled") renderBenchmarks(results[0].value);
    else {
      requiredElement("benchmark-table-wrap").hidden = true;
      status.textContent = `Evaluation artifact unavailable: ${results[0].reason instanceof Error ? results[0].reason.message : "backend request failed"}.`;
    }
    if (results[1].status === "fulfilled") renderLimits(results[1].value);
    else renderLimits(null);
  }
}

