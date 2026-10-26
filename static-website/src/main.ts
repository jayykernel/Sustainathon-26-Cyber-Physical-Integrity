import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "./style.css";

import { api, toTimelineSample, type BackendEvent, type BackendFrame, type Scenario } from "./api";
import { STAGE_COUNT } from "./config";
import type { Classification } from "./sim/classifier";
import type { TimelineSample } from "./sim/timeline";
import { stageFloatForProgress } from "./stages";
import { SimulationWorld } from "./scene/world";
import { AttackerTerminal } from "./ui/hacker";
import { Hud } from "./ui/hud";
import { TemperatureChart } from "./ui/chart";
import { classificationLabel } from "./ui/format";

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
  const live = requireElement("live-region");
  const alarmWash = requireElement("alarm-wash");
  const scenarioSelect = requireElement<HTMLSelectElement>("scenario-select");
  const seedInput = requireElement<HTMLInputElement>("seed-input");
  const speedSelect = requireElement<HTMLSelectElement>("speed-select");
  const startButton = requireElement<HTMLButtonElement>("start-run");
  const pauseButton = requireElement<HTMLButtonElement>("pause-run");
  const injectButton = requireElement<HTMLButtonElement>("inject-run");
  const attackSelect = requireElement<HTMLSelectElement>("attack-select");
  const statusText = requireElement("run-status");
  const connectionText = requireElement("connection-state");
  const configHash = requireElement("channel");
  const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  let reducedMotion = motionQuery.matches;
  motionQuery.addEventListener("change", (event) => { reducedMotion = event.matches; });
  let socket: WebSocket | null = null;
  let sessionId: string | null = null;
  let currentSample: TimelineSample | null = null;
  let duration: number = 3600;
  let paused = false;
  let elapsed = 0;
  let lastTimestamp = 0;
  let bootHidden = false;
  let announcedClassification: Classification | null = null;
  const pointerTarget = { x: 0, y: 0 };
  const pointer = { x: 0, y: 0 };

  const setStatus = (message: string, state = "") => {
    statusText.textContent = message;
    statusText.dataset.state = state;
  };
  const closeSession = async () => {
    const previous = sessionId;
    sessionId = null;
    socket?.close(); socket = null;
    if (previous) void api.deleteSession(previous).catch(() => undefined);
    pauseButton.disabled = true;
    injectButton.disabled = true;
    pauseButton.textContent = "Pause";
  };

  try {
    const [health, scenarios] = await Promise.all([api.health(), api.scenarios()]);
    connectionText.textContent = "Backend ready";
    connectionText.title = `Config ${health.config_hash}`;
    configHash.title = `Localization channel · config ${health.config_hash}`;
    scenarioSelect.replaceChildren(...scenarios.map((scenario: Scenario) => {
      const option = document.createElement("option");
      option.value = scenario.id;
      option.textContent = `${scenario.title} · ${scenario.level}`;
      return option;
    }));
    scenarioSelect.disabled = false;
    startButton.disabled = false;
    setStatus(`Backend connected · ${scenarios.length} scenarios`);
  } catch (error) {
    connectionText.textContent = "Backend offline";
    setStatus(error instanceof Error ? error.message : "Backend unavailable", "error");
    showBootError("The simulation backend is unavailable.", "Start the backend and reload this page. This interface uses live backend sessions.");
    return;
  }

  const startRun = async () => {
    await closeSession();
    hud.reset(); terminal.reset(); currentSample = null; duration = 3600;
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
        let message: { type: string; frames?: BackendFrame[]; t?: number; kind?: string; severity?: string; text?: string; message?: string; summary?: { steps?: number } };
        try { message = JSON.parse(event.data) as typeof message; }
        catch { setStatus("Received an invalid backend message", "error"); return; }
        if (message.type === "frame_batch" && message.frames) {
          for (const frame of message.frames) {
            duration = Math.max(duration, frame.t);
            currentSample = toTimelineSample(frame, duration);
            hud.update(currentSample);
            if (announcedClassification !== currentSample.classification) {
              announcedClassification = currentSample.classification;
              live.textContent = `Backend response state ${classificationLabel(currentSample.classification)}.`;
            }
          }
          setStatus(paused ? "Session paused" : `Live session · ${Math.round((currentSample?.t ?? 0) / 60)} min simulated`);
        } else if (message.type === "event") {
          terminal.update({ t: message.t ?? 0, kind: message.kind ?? "event", severity: message.severity ?? "info", text: message.text ?? "Backend event" } satisfies BackendEvent);
        } else if (message.type === "done") {
          setStatus(`Run complete · ${message.summary?.steps ?? ""} steps`);
          pauseButton.disabled = true; injectButton.disabled = true;
        } else if (message.type === "error") {
          setStatus(message.message ?? "Backend session error", "error");
        }
      };
      ws.onerror = () => setStatus("Live connection failed", "error");
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
  pauseButton.addEventListener("click", () => {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    paused = !paused;
    socket.send(JSON.stringify({ type: paused ? "pause" : "resume" }));
    pauseButton.textContent = paused ? "Resume" : "Pause";
    setStatus(paused ? "Session paused" : "Live session resumed");
  });
  speedSelect.addEventListener("change", () => {
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "speed", value: Number(speedSelect.value) }));
  });
  injectButton.addEventListener("click", () => {
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "inject", attack: attackSelect.value }));
      setStatus(`Injecting ${attackSelect.value} at the current simulation time…`);
    }
  });
  window.addEventListener("pointermove", (event) => {
    pointerTarget.x = (event.clientX / window.innerWidth) * 2 - 1;
    pointerTarget.y = -((event.clientY / window.innerHeight) * 2 - 1);
  }, { passive: true });

  const scrollStageFloat = (): number => {
    const viewport = Math.max(1, window.innerHeight);
    return stageFloatForProgress(window.scrollY / (STAGE_COUNT * viewport));
  };
  let displayStageFloat = scrollStageFloat();
  const frame = (timestamp: number) => {
    const dt = lastTimestamp === 0 ? 0 : Math.min(0.05, (timestamp - lastTimestamp) / 1000);
    lastTimestamp = timestamp; elapsed += dt;
    const targetStageFloat = scrollStageFloat();
    if (reducedMotion) displayStageFloat = targetStageFloat;
    else displayStageFloat += (targetStageFloat - displayStageFloat) * (1 - Math.exp(-dt * 7));
    const blend = reducedMotion ? 1 : Math.min(1, dt * 6);
    pointer.x += (pointerTarget.x - pointer.x) * blend;
    pointer.y += (pointerTarget.y - pointer.y) * blend;
    if (currentSample) {
      world.render({ sample: currentSample, stageFloat: displayStageFloat, elapsed, dt, pointer, scrollVelocity: 0, reducedMotion });
      alarmWash.classList.toggle("is-active", currentSample.alarm);
    }
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
