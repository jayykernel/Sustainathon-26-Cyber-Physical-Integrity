import { api, type BackendFrame, type IncidentAlert } from "../api";
import type { VehicleType } from "../scene/world";

const ALERT_QUEUE_KEY = "physiguard:pending-driver-alerts:v1";
const EVIDENCE_KEY_PREFIX = "physiguard:incident-evidence:v1:";
const MAX_EVIDENCE_FRAMES = 120;

interface EvidenceFrame {
  recorded_at: string;
  simulation_time_s: number;
  response_state: string;
  suspected_path: string;
  localization_confidence: number;
  nis: number;
  temperature_residual_c: number;
  requested_current_a: number;
  guarded_current_a: number;
  control_mode: string;
  attack_active: boolean;
}

function readPendingAlerts(): IncidentAlert[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(ALERT_QUEUE_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed as IncidentAlert[] : [];
  } catch {
    return [];
  }
}

/** A driver-facing incident preview and store-and-forward alert queue for the demo. */
export class DriverDisplay {
  private readonly panel = document.getElementById("driver-display") as HTMLElement;
  private readonly title = document.getElementById("driver-display-title") as HTMLElement;
  private readonly stateLabel = document.getElementById("driver-alert-state") as HTMLElement;
  private readonly guidance = document.getElementById("driver-guidance") as HTMLElement;
  private readonly suspectPath = document.getElementById("driver-suspect-path") as HTMLElement;
  private readonly assistState = document.getElementById("driver-assist-state") as HTMLElement;
  private readonly evidenceState = document.getElementById("driver-evidence-state") as HTMLElement;
  private readonly delivery = document.getElementById("alert-delivery") as HTMLElement;
  private readonly safeStopButton = document.getElementById("request-safe-stop") as HTMLButtonElement;
  private readonly evidenceButton = document.getElementById("save-evidence") as HTMLButtonElement;
  private readonly emergencyButton = document.getElementById("emergency-send") as HTMLButtonElement;
  private readonly closeButton = document.getElementById("close-driver-alert") as HTMLButtonElement;
  private readonly reopenButton = document.getElementById("open-driver-alert") as HTMLButtonElement;
  private pendingAlerts = readPendingAlerts();
  private evidenceFrames: EvidenceFrame[] = [];
  private incidentId: string | null = null;
  private latestFrame: BackendFrame | null = null;
  private vehicleType: VehicleType = "car";
  private scenarioId = "";
  private seed = 0;
  private assistanceAvailable = true;
  private automaticStopPreviewed = false;
  private lastWasIncident = false;
  private dismissed = false;
  private lastState = "NORMAL";
  private sending = false;

  constructor() {
    this.safeStopButton.addEventListener("click", () => this.previewSafeStopRequest(true));
    this.evidenceButton.addEventListener("click", () => this.downloadEvidence());
    this.emergencyButton.addEventListener("click", () => void this.forceSendAlert());
    this.closeButton.addEventListener("click", () => this.dismiss());
    this.reopenButton.addEventListener("click", () => this.reopen());
    if (this.pendingAlerts.length > 0) {
      this.delivery.textContent = `${this.pendingAlerts.length} emergency alert(s) waiting on this device for a connection.`;
    }
  }

  beginRun(): void {
    this.panel.hidden = true;
    this.reopenButton.hidden = true;
    this.evidenceFrames = [];
    this.incidentId = null;
    this.latestFrame = null;
    this.automaticStopPreviewed = false;
    this.lastWasIncident = false;
    this.dismissed = false;
    this.lastState = "NORMAL";
    this.safeStopButton.disabled = false;
    this.assistState.textContent = "Waiting for vehicle state";
    this.evidenceState.textContent = "Waiting for an incident";
    this.delivery.textContent = this.pendingAlerts.length > 0
      ? `${this.pendingAlerts.length} emergency alert(s) waiting on this device for a connection.`
      : "Emergency alert is ready.";
  }

  configure(vehicleType: VehicleType, assistanceAvailable: boolean, scenarioId: string, seed: number): void {
    this.vehicleType = vehicleType;
    this.assistanceAvailable = assistanceAvailable;
    this.scenarioId = scenarioId;
    this.seed = seed;
    if (this.latestFrame && this.latestFrame.state !== "NORMAL") this.render(this.latestFrame);
  }

  render(frame: BackendFrame): void {
    this.latestFrame = frame;
    const state = frame.state.toUpperCase();
    if (state === "NORMAL") {
      if (this.lastWasIncident) {
        this.incidentId = null;
        this.evidenceFrames = [];
        this.automaticStopPreviewed = false;
        this.dismissed = false;
      }
      this.captureEvidence(frame, state, false);
      this.lastWasIncident = false;
      this.lastState = state;
      this.panel.hidden = true;
      this.reopenButton.hidden = true;
      return;
    }
    if (
      (this.lastState === "SUSPECT" && state === "CONFIRMED")
      || (this.lastState !== "SAFE_MODE" && state === "SAFE_MODE")
    ) {
      this.dismissed = false;
    }
    this.lastWasIncident = true;
    this.lastState = state;

    this.panel.hidden = this.dismissed;
    this.reopenButton.hidden = !this.dismissed;
    this.title.textContent = this.vehicleType === "car" ? "Car battery-system alert" : "Two-wheeler battery-system alert";
    if (state === "SAFE_MODE") {
      this.stateLabel.textContent = "SAFE MODE";
      this.guidance.textContent = this.vehicleType === "car"
        ? "Vehicle protection is in safe mode. If moving, continue only as the vehicle permits and stop in a safe place. Request qualified roadside or service support."
        : "Vehicle protection is in safe mode. Keep both hands on the controls and stop at a safe location. Do not handle the display while moving; request qualified roadside or service support. ";
    } else if (state === "CONFIRMED") {
      this.stateLabel.textContent = "HIGH PRIORITY";
      this.guidance.textContent = this.vehicleType === "car"
        ? "A battery-system integrity threat is confirmed by the simulation. Keep attention on the road and make a controlled stop when safe; do not perform a sudden shutdown."
        : "A battery-system integrity threat is confirmed by the simulation. Keep both hands on the controls, reduce demand only if safe, and pull over when safe. Do not use the display while moving.";
    } else {
      this.stateLabel.textContent = "CHECK VEHICLE";
      this.guidance.textContent = this.vehicleType === "car"
        ? "A battery telemetry anomaly is under investigation. Keep attention on driving and move to a safe stopping place when conditions allow. This alert alone does not prove malware."
        : "A battery telemetry anomaly is under investigation. Keep both hands on the controls and pull over when conditions allow. This alert alone does not prove malware.";
    }
    this.suspectPath.textContent = frame.localization.channel || "Battery telemetry · path unresolved";
    this.safeStopButton.disabled = !this.assistanceAvailable;
    this.assistState.textContent = !this.assistanceAvailable
      ? "Not available · driver guidance only"
      : state === "CONFIRMED" || state === "SAFE_MODE"
        ? "Automatic safe-stop request previewed · awaiting vehicle acknowledgement"
        : "Available · waiting for stronger evidence";
    if ((state === "CONFIRMED" || state === "SAFE_MODE") && this.assistanceAvailable && !this.automaticStopPreviewed) {
      this.automaticStopPreviewed = true;
      this.safeStopButton.textContent = "Safe-stop request previewed";
    } else if (!this.automaticStopPreviewed) {
      this.safeStopButton.textContent = "Request safe-stop assist";
    }
    this.captureEvidence(frame, state, true);
  }

  private dismiss(): void {
    this.dismissed = true;
    this.panel.hidden = true;
    this.reopenButton.hidden = false;
  }

  private reopen(): void {
    this.dismissed = false;
    this.panel.hidden = false;
    this.reopenButton.hidden = true;
  }

  async retryPendingAlerts(): Promise<void> {
    if (this.sending || !navigator.onLine || this.pendingAlerts.length === 0) return;
    this.sending = true;
    try {
      while (this.pendingAlerts.length > 0) {
        const next = this.pendingAlerts[0];
        const acknowledgement = await api.sendIncidentAlert(next);
        if (!acknowledgement.received) break;
        this.pendingAlerts.shift();
        this.persistPendingAlerts();
        this.delivery.textContent = acknowledgement.duplicate
          ? "Monitoring backend already has this alert. It is acknowledged; no emergency service was contacted."
          : "Monitoring backend acknowledged the alert. No emergency service was contacted by this demo.";
      }
    } catch {
      this.delivery.textContent = "No path to the monitoring backend. Alert remains saved on this device and will retry when connected.";
    } finally {
      this.sending = false;
    }
  }

  private previewSafeStopRequest(manual: boolean): void {
    if (!this.latestFrame || !this.assistanceAvailable) return;
    this.automaticStopPreviewed = true;
    this.assistState.textContent = manual
      ? "Manual safe-stop request previewed · waiting for vehicle acknowledgement"
      : "Automatic safe-stop request previewed · awaiting vehicle acknowledgement";
    this.safeStopButton.textContent = "Request previewed";
  }

  private async forceSendAlert(): Promise<void> {
    if (!this.latestFrame || this.latestFrame.state === "NORMAL") return;
    const alert: IncidentAlert = {
      alert_id: globalThis.crypto?.randomUUID?.() ?? `pg-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      created_at: new Date().toISOString(),
      vehicle_type: this.vehicleType,
      state: this.latestFrame.state === "SUSPECT" ? "suspect" : "confirmed",
      suspected_path: this.latestFrame.localization.channel || "Battery telemetry · path unresolved",
      simulation_time_s: this.latestFrame.t,
      force: true,
    };
    this.pendingAlerts.push(alert);
    this.persistPendingAlerts();
    this.delivery.textContent = "Emergency alert force-send requested. Attempting the monitoring backend; if offline, it stays queued on this device.";
    await this.retryPendingAlerts();
  }

  private captureEvidence(frame: BackendFrame, state: string, incidentActive: boolean): void {
    this.evidenceFrames.push({
      recorded_at: new Date().toISOString(),
      simulation_time_s: frame.t,
      response_state: state,
      suspected_path: frame.localization.channel || "unresolved",
      localization_confidence: frame.localization.confidence,
      nis: frame.evidence.nis,
      temperature_residual_c: frame.residual.temp,
      requested_current_a: frame.control.i_req,
      guarded_current_a: frame.control.i_safe,
      control_mode: frame.control.mode,
      attack_active: frame.attack.active,
    });
    if (this.evidenceFrames.length > MAX_EVIDENCE_FRAMES) this.evidenceFrames.shift();
    if (!incidentActive) return;
    if (!this.incidentId) this.incidentId = globalThis.crypto?.randomUUID?.() ?? `pg-${Date.now()}`;
    const record = {
      incident_id: this.incidentId,
      vehicle_type: this.vehicleType,
      scenario_id: this.scenarioId,
      seed: this.seed,
      prototype_notice: "Simulation evidence only; not a vehicle diagnostic record.",
      frames: this.evidenceFrames,
    };
    try {
      localStorage.setItem(`${EVIDENCE_KEY_PREFIX}${this.incidentId}`, JSON.stringify(record));
      this.evidenceState.textContent = `${this.evidenceFrames.length} frames saved on this device`;
    } catch {
      this.evidenceState.textContent = "Local evidence storage unavailable · download a copy";
    }
  }

  private downloadEvidence(): void {
    if (!this.incidentId) {
      this.evidenceState.textContent = "No incident evidence to download yet";
      return;
    }
    const data = localStorage.getItem(`${EVIDENCE_KEY_PREFIX}${this.incidentId}`);
    if (!data) {
      this.evidenceState.textContent = "Evidence was not available in local storage";
      return;
    }
    const url = URL.createObjectURL(new Blob([data], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `physiguard-incident-${this.incidentId}.json`;
    link.click();
    URL.revokeObjectURL(url);
    this.evidenceState.textContent = "Evidence file downloaded";
  }

  private persistPendingAlerts(): void {
    try { localStorage.setItem(ALERT_QUEUE_KEY, JSON.stringify(this.pendingAlerts)); }
    catch { this.delivery.textContent = "This browser could not save the alert locally. Keep this page open and restore connectivity."; }
  }
}
