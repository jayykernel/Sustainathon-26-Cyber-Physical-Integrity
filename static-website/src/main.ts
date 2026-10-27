import "@fontsource/manrope/latin-300.css";
import "@fontsource/manrope/latin-400.css";
import "@fontsource/manrope/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "./design-tokens.css";
import "./style.css";

import { api, createIdleSample, loadRecordedRun, OFFLINE_SCENARIOS, toTimelineSample, type BackendEvent, type BackendFrame, type Scenario } from "./api";
import type { Classification } from "./sim/classifier";
import type { TimelineSample } from "./sim/timeline";
import { SimulationWorld, type VehicleType } from "./scene/world";
import { AttackerTerminal } from "./ui/hacker";
import { Hud } from "./ui/hud";
import { TemperatureChart } from "./ui/chart";
import { classificationLabel } from "./ui/format";
import { DriverDisplay } from "./ui/driverDisplay";
import { ResearchView } from "./ui/research";

function requireElement<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Missing required element #${id}`);
  return element as T;
}

function showBootError(title: string, message: string): void {
  const boot = requireElement("boot");
  const bootTitle = boot.querySelector<HTMLElement>(".boot__title");
  if (bootTitle) bootTitle.textContent = title;
  requireElement("boot-text").textContent = message;
  boot.classList.add("is-error");
}

async function start(): Promise<void> {
  const canvas = requireElement<HTMLCanvasElement>("scene");
  const boot = requireElement("boot");
  let world: SimulationWorld;
  try { world = new SimulationWorld(canvas); }
  catch (error) {
    console.error(error);
    showBootError("The 3D scene could not start.", "This browser could not create a WebGL context. Try a current browser with hardware acceleration enabled.");
    return;
  }

  const chart = new TemperatureChart(requireElement<HTMLCanvasElement>("chart"));
  const hud = new Hud(chart);
  const terminal = new AttackerTerminal();
  const driverDisplay = new DriverDisplay();
  const live = requireElement("live-region");
  const alarmWash = requireElement("alarm-wash");
  const incidentOverlay = requireElement("incident-overlay");
  const incidentContinue = requireElement<HTMLButtonElement>("incident-continue");
  const scenarioSelect = requireElement<HTMLSelectElement>("scenario-select");
  const researchView = new ResearchView(scenarioSelect);
  void researchView.load();
  const vehicleTypeSelect = requireElement<HTMLSelectElement>("vehicle-type");
  const assistProfileSelect = requireElement<HTMLSelectElement>("assist-profile");
  const seedInput = requireElement<HTMLInputElement>("seed-input");
  const speedSelect = requireElement<HTMLSelectElement>("speed-select");
  const startButton = requireElement<HTMLButtonElement>("start-run");
  const pauseButton = requireElement<HTMLButtonElement>("pause-run");
  const replayButton = requireElement<HTMLButtonElement>("load-replay");
  const replayNotice = requireElement("replay-notice");
  const injectButton = requireElement<HTMLButtonElement>("inject-run");
  const operatorResetButton = requireElement<HTMLButtonElement>("operator-reset");
  const attackSelect = requireElement<HTMLSelectElement>("attack-select");
  const statusText = requireElement("run-status");
  const connectionText = requireElement("connection-state");
  const configHash = requireElement("channel");
  const classifierToggle = requireElement<HTMLButtonElement>("classifier-toggle");
  const classifierPanel = classifierToggle.closest<HTMLElement>(".hud__status");
  const classifierDetails = requireElement<HTMLElement>("classifier-details");
  const setClassifierOpen = (open: boolean) => {
    classifierToggle.setAttribute("aria-expanded", String(open));
    classifierDetails.setAttribute("aria-hidden", String(!open));
    classifierDetails.inert = !open;
    classifierPanel?.classList.toggle("is-open", open);
  };
  setClassifierOpen(true);
  classifierToggle.addEventListener("click", () => {
    setClassifierOpen(classifierToggle.getAttribute("aria-expanded") !== "true");
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && classifierToggle.getAttribute("aria-expanded") === "true") {
      setClassifierOpen(false);
      classifierToggle.focus();
    }
  });
  document.addEventListener("pointerdown", (event) => {
    if (classifierToggle.getAttribute("aria-expanded") !== "true") return;
    if (event.target instanceof Node && !classifierPanel?.contains(event.target) && !classifierDetails.contains(event.target)) {
      setClassifierOpen(false);
    }
  });
  const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  let reducedMotion = motionQuery.matches;
  motionQuery.addEventListener("change", (event) => { reducedMotion = event.matches; });
  let socket: WebSocket | null = null;
  let sessionId: string | null = null;
  let currentSample: TimelineSample = createIdleSample();
  let duration: number = 3600;
  let paused = false;
  let replayMode = false;
  let replayFrames: BackendFrame[] = [];
  let replayEvents: BackendEvent[] = [];
  let replayElapsed = 0;
  let replayIndex = -1;
  let replayEventIndex = 0;
  let elapsed = 0;
  let lastTimestamp = 0;
  let bootHidden = false;
  let announcedClassification: Classification | null = null;
  let incidentAnnounced = false;
  let resetInProgress = false;
  let safeModeActive = false;
  let liveBackendAvailable = false;
  let overlayTimer: number | null = null;
  let focusTimer: number | null = null;
  let incidentFocus = 0;
  let incidentFocusTarget = 0;

  const setStatus = (message: string, state = "") => {
    statusText.textContent = message;
    statusText.dataset.state = state;
  };
  const closeIncidentOverlay = () => {
    incidentOverlay.classList.remove("is-active");
    incidentOverlay.setAttribute("aria-hidden", "true");
    incidentOverlay.inert = true;
    document.body.classList.remove("incident-impact");
    if (overlayTimer !== null) window.clearTimeout(overlayTimer);
    overlayTimer = null;
  };
  const showIncidentOverlay = () => {
    incidentOverlay.inert = false;
    incidentOverlay.setAttribute("aria-hidden", "false");
    incidentOverlay.classList.add("is-active");
    document.body.classList.add("incident-impact");
    window.requestAnimationFrame(() => incidentContinue.focus());
    if (!reducedMotion) overlayTimer = window.setTimeout(closeIncidentOverlay, 6500);
  };
  const returnToOverview = () => {
    incidentFocusTarget = 0;
    if (focusTimer !== null) window.clearTimeout(focusTimer);
    focusTimer = null;
  };
  const focusOnIncident = () => {
    incidentFocusTarget = 1;
    if (focusTimer !== null) window.clearTimeout(focusTimer);
    focusTimer = window.setTimeout(() => {
      incidentFocusTarget = 0;
      focusTimer = null;
    }, 2800);
  };
  const selectedVehicleType = (): VehicleType => vehicleTypeSelect.value === "two_wheeler" ? "two_wheeler" : "car";
  const configureDriverDisplay = () => driverDisplay.configure(
    selectedVehicleType(),
    assistProfileSelect.value === "available",
    scenarioSelect.value,
    Math.max(0, Math.floor(Number(seedInput.value) || 0)),
  );
  const closeSession = async () => {
    const previous = sessionId;
    sessionId = null;
    socket?.close(); socket = null;
    if (previous) void api.deleteSession(previous).catch(() => undefined);
    pauseButton.disabled = true;
    injectButton.disabled = true;
    pauseButton.textContent = "Pause";
  };

  const showReplayFrame = (index: number) => {
    if (index < 0 || index >= replayFrames.length || index === replayIndex) return;
    replayIndex = index;
    const frame = replayFrames[index];
    currentSample = toTimelineSample(frame, duration);
    hud.update(currentSample);
    driverDisplay.render(frame);
    while (replayEventIndex < replayEvents.length && replayEvents[replayEventIndex].t <= frame.t) {
      terminal.update(replayEvents[replayEventIndex]);
      replayEventIndex += 1;
    }
    if (announcedClassification !== currentSample.classification) {
      announcedClassification = currentSample.classification;
      live.textContent = `Recorded replay response state ${classificationLabel(currentSample.classification)}.`;
    }
    if (currentSample.classification === "safe" && incidentAnnounced) {
      incidentAnnounced = false;
      returnToOverview();
      closeIncidentOverlay();
    } else if (currentSample.classification !== "safe" && !incidentAnnounced) {
      incidentAnnounced = true;
      focusOnIncident();
      showIncidentOverlay();
    }
  };

  const loadReplay = async () => {
    try {
      await closeSession();
      const run = await loadRecordedRun(scenarioSelect.value);
      closeIncidentOverlay();
      document.body.dataset.mode = "replay";
      document.body.classList.remove("incident-active");
      replayNotice.hidden = false;
      replayMode = true;
      replayFrames = run.frames;
      replayEvents = run.events;
      replayElapsed = 0;
      replayIndex = -1;
      replayEventIndex = 0;
      duration = 3600;
      announcedClassification = "safe";
      incidentAnnounced = false;
      paused = false;
      hud.reset();
      terminal.reset();
      driverDisplay.beginRun();
      startButton.disabled = !liveBackendAvailable;
      startButton.hidden = !liveBackendAvailable;
      pauseButton.disabled = false;
      pauseButton.hidden = false;
      injectButton.disabled = true;
      operatorResetButton.disabled = true;
      pauseButton.textContent = "Pause";
      configHash.title = `Recorded run config ${run.config_hash} · seed ${run.seed}`;
      setStatus(`Replay loaded · seed ${run.seed} · recorded only`);
      showReplayFrame(0);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Recorded replay unavailable", "error");
    }
  };

  try {
    const [health, scenarios] = await Promise.all([api.health(), api.scenarios()]);
    if (health.status !== "ok" || !health.thresholds_loaded) {
      throw new Error(health.detection_error || "Calibrated detection thresholds are unavailable");
    }
    liveBackendAvailable = true;
    startButton.hidden = false;
    pauseButton.hidden = false;
    document.body.dataset.mode = "live";
    connectionText.textContent = "Backend ready";
    connectionText.title = `Config ${health.config_hash}`;
    configHash.title = `Localization channel · config ${health.config_hash}`;
    scenarioSelect.replaceChildren(...scenarios.map((scenario: Scenario) => {
      const option = document.createElement("option");
      option.value = scenario.id;
      option.textContent = `${scenario.title} · ${scenario.level}`;
      return option;
    }));
    researchView.updateScenarios(scenarios);
    scenarioSelect.disabled = false;
    startButton.disabled = false;
    setStatus(`Backend connected · ${scenarios.length} scenarios`);
    void driverDisplay.retryPendingAlerts();
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : "Backend unavailable";
    connectionText.textContent = errorMessage.includes("Calibrated detection thresholds")
      ? "Calibration unavailable"
      : "Backend unavailable";
    liveBackendAvailable = false;
    document.body.dataset.mode = "offline";
    scenarioSelect.replaceChildren(...OFFLINE_SCENARIOS.map((scenario) => {
      const option = document.createElement("option");
      option.value = scenario.id;
      option.textContent = `${scenario.title} · recorded run`;
      return option;
    }));
    researchView.updateScenarios(OFFLINE_SCENARIOS);
    scenarioSelect.disabled = false;
    startButton.disabled = true;
    startButton.hidden = true;
    pauseButton.disabled = true;
    pauseButton.hidden = true;
    injectButton.disabled = true;
    operatorResetButton.disabled = true;
    replayButton.hidden = false;
    replayNotice.hidden = true;
    setStatus(`${errorMessage} · recorded-run replay is available`, "error");
  }

  const startRun = async () => {
    replayMode = false;
    replayFrames = [];
    replayEvents = [];
    replayNotice.hidden = true;
    document.body.dataset.mode = "live";
    await closeSession();
    closeIncidentOverlay();
    document.body.classList.remove("incident-active");
    returnToOverview();
    incidentAnnounced = false;
    incidentFocus = 0;
    resetInProgress = false;
    safeModeActive = false;
    driverDisplay.beginRun();
    configureDriverDisplay();
    operatorResetButton.disabled = true;
    hud.reset(); terminal.reset(); currentSample = createIdleSample(); duration = 3600;
    paused = false;
    startButton.disabled = true;
    pauseButton.disabled = true;
    injectButton.disabled = true;
    setStatus("Preparing backend simulation…");
    try {
      const seed = Math.max(0, Math.min(4294967295, Math.floor(Number(seedInput.value) || 0)));
      seedInput.value = String(seed);
      const { session_id: id } = await api.createSession(scenarioSelect.value, seed, Number(speedSelect.value));
      sessionId = id;
      setStatus(`Session ${id.slice(0, 8)} · waiting for simulation`);
      const protocol = location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(`${protocol}//${location.host}/api/sessions/${id}/ws`);
      socket = ws;
      ws.onopen = () => {
        if (socket !== ws) return;
        pauseButton.disabled = false; injectButton.disabled = false;
        setStatus(`Live session ${id.slice(0, 8)}`);
      };
      ws.onmessage = (event) => {
        if (socket !== ws) return;
        let message: { type: string; frames?: BackendFrame[]; t?: number; kind?: string; severity?: string; text?: string; message?: string; data?: { accepted?: boolean; completed?: boolean }; summary?: { steps?: number } };
        try { message = JSON.parse(event.data) as typeof message; }
        catch { setStatus("Received an invalid backend message", "error"); return; }
        if (message.type === "frame_batch" && message.frames) {
          for (const frame of message.frames) {
            const previousClassification = announcedClassification;
            duration = Math.max(duration, frame.t);
            currentSample = toTimelineSample(frame, duration);
            hud.update(currentSample);
            driverDisplay.render(frame);
            if (announcedClassification !== currentSample.classification) {
              announcedClassification = currentSample.classification;
              live.textContent = `Backend response state ${classificationLabel(currentSample.classification)}.`;
            }
            if (currentSample.classification === "safe" && incidentAnnounced) {
              incidentAnnounced = false;
              returnToOverview();
              closeIncidentOverlay();
            } else if (currentSample.classification !== "safe" && !incidentAnnounced) {
              incidentAnnounced = true;
              focusOnIncident();
              showIncidentOverlay();
            } else if (previousClassification === "suspect" && currentSample.classification === "confirmed") {
              focusOnIncident();
            }
            safeModeActive = frame.state === "SAFE_MODE";
            if (safeModeActive) operatorResetButton.disabled = resetInProgress;
            else {
              resetInProgress = false;
              operatorResetButton.disabled = true;
            }
          }
          if (paused) setStatus("Session paused");
          else if (message.frames.at(-1)?.state === "SAFE_MODE") setStatus("Simulation safe mode active · driver guidance shown");
          else if (currentSample.classification === "confirmed") setStatus("Simulation threat confirmed · driver warning shown");
          else if (currentSample.classification === "suspect") setStatus("Simulation anomaly under review · driver warning shown");
          else setStatus(`Live session · ${Math.round(currentSample.t / 60)} min simulated`);
        } else if (message.type === "event") {
          terminal.update({ t: message.t ?? 0, kind: message.kind ?? "event", severity: message.severity ?? "info", text: message.text ?? "Backend event" } satisfies BackendEvent);
          if (message.kind === "operator_reset") {
            resetInProgress = Boolean(message.data?.accepted);
            operatorResetButton.disabled = resetInProgress || !safeModeActive;
            setStatus(message.data?.accepted ? "Operator reset accepted · replaying with clean-check sequence" : (message.text ?? "Operator reset unavailable"), message.data?.accepted ? "" : "error");
          }
        } else if (message.type === "done") {
          setStatus(`Run complete · ${message.summary?.steps ?? ""} steps`);
          pauseButton.disabled = true; injectButton.disabled = true;
        } else if (message.type === "error") {
          setStatus(message.message ?? "Backend session error", "error");
        }
      };
      ws.onerror = () => {
        replayButton.hidden = false;
        setStatus("Live connection failed · recorded-run replay is available", "error");
      };
      ws.onclose = () => {
        if (socket === ws) {
          socket = null;
          pauseButton.disabled = true; injectButton.disabled = true;
        }
      };
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not start the simulation", "error");
    } finally {
      startButton.disabled = false;
    }
  };

  startButton.addEventListener("click", () => void startRun());
  replayButton.addEventListener("click", () => void loadReplay());
  pauseButton.addEventListener("click", () => {
    if (replayMode) {
      paused = !paused;
      pauseButton.textContent = paused ? "Resume" : "Pause";
      setStatus(paused ? "Recorded replay paused · not live data" : "Recorded replay playing · not live data");
      return;
    }
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    paused = !paused;
    socket.send(JSON.stringify({ type: paused ? "pause" : "resume" }));
    pauseButton.textContent = paused ? "Resume" : "Pause";
    setStatus(paused ? "Session paused" : "Live session resumed");
  });
  speedSelect.addEventListener("change", () => {
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "speed", value: Number(speedSelect.value) }));
    else if (replayMode) setStatus(`Recorded replay · ${speedSelect.value}× · not live data`);
  });
  injectButton.addEventListener("click", () => {
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "inject", attack: attackSelect.value }));
      terminal.notify(`${attackSelect.value} injected · awaiting backend telemetry`);
      setStatus(`Injecting ${attackSelect.value} at the current simulation time…`);
    }
  });
  incidentContinue.addEventListener("click", closeIncidentOverlay);
  requireElement<HTMLButtonElement>("close-driver-alert").addEventListener("click", returnToOverview);
  operatorResetButton.addEventListener("click", () => {
    if (!socket || socket.readyState !== WebSocket.OPEN || operatorResetButton.disabled) return;
    resetInProgress = true;
    operatorResetButton.disabled = true;
    socket.send(JSON.stringify({ type: "operator_reset" }));
    setStatus("Requesting controlled operator reset…");
  });
  vehicleTypeSelect.addEventListener("change", configureDriverDisplay);
  assistProfileSelect.addEventListener("change", configureDriverDisplay);
  scenarioSelect.addEventListener("change", configureDriverDisplay);
  requireElement<HTMLButtonElement>("overview-button").addEventListener("click", () => {
    returnToOverview();
    closeIncidentOverlay();
  });
  window.addEventListener("online", () => void driverDisplay.retryPendingAlerts());
  // The analysis dashboard is stationary; the vehicle scene only responds to
  // live incident focus and no longer uses page scroll as a camera control.
  const displayStageFloat = 0;
  const frame = (timestamp: number) => {
    const dt = lastTimestamp === 0 ? 0 : Math.min(0.05, (timestamp - lastTimestamp) / 1000);
    lastTimestamp = timestamp; elapsed += dt;
    if (replayMode && !paused && replayFrames.length > 0) {
      replayElapsed += dt * Number(speedSelect.value);
      let nextIndex = Math.max(0, replayIndex);
      while (nextIndex < replayFrames.length - 1 && replayFrames[nextIndex + 1].t <= replayElapsed) nextIndex += 1;
      showReplayFrame(nextIndex);
      if (nextIndex === replayFrames.length - 1) {
        paused = true;
        pauseButton.disabled = true;
        pauseButton.textContent = "Replay complete";
        setStatus("Recorded replay complete · not live data");
      }
    }
    const focusBlend = reducedMotion ? 1 : 1 - Math.exp(-dt * 3.2);
    incidentFocus += (incidentFocusTarget - incidentFocus) * focusBlend;
    world.render({ sample: currentSample, stageFloat: displayStageFloat, elapsed, dt, scrollVelocity: 0, reducedMotion, vehicleType: selectedVehicleType(), incidentFocus });
    alarmWash.classList.toggle("is-active", currentSample.alarm);
    document.body.dataset.state = currentSample.classification;
    document.body.classList.toggle("incident-active", currentSample.classification !== "safe");
    if (!bootHidden) {
      bootHidden = true; boot.classList.add("is-hidden"); boot.setAttribute("aria-hidden", "true");
    }
    requestAnimationFrame(frame);
  };
  window.addEventListener("resize", () => { world.resize(); chart.resize(); }, { passive: true });
  window.addEventListener("pagehide", () => { socket?.close(); if (sessionId) void api.deleteSession(sessionId); world.dispose(); chart.disconnect(); }, { once: true });
  requestAnimationFrame(frame);
}

void start();
