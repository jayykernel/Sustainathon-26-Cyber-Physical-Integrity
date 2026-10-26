import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "./style.css";

import { STAGE_COUNT } from "./config";
import { SimulationWorld } from "./scene/world";
import type { Classification } from "./sim/classifier";
import { buildTimeline } from "./sim/timeline";
import { STAGES, simTimeForStageFloat, stageFloatForProgress } from "./stages";
import { TemperatureChart } from "./ui/chart";
import { classificationLabel } from "./ui/format";
import { AttackerTerminal } from "./ui/hacker";
import { Hud } from "./ui/hud";

function requireElement<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Missing required element #${id}`);
  return element as T;
}

function showBootError(title: string, message: string): void {
  const boot = requireElement("boot");
  const bootTitle = boot.querySelector<HTMLElement>(".boot__title");
  const bootText = requireElement("boot-text");
  boot.classList.add("is-error");
  if (bootTitle) bootTitle.textContent = title;
  bootText.textContent = message;
}

function start(): void {
  const timeline = buildTimeline();
  const canvas = requireElement<HTMLCanvasElement>("scene");
  const boot = requireElement("boot");

  let world: SimulationWorld;
  try {
    world = new SimulationWorld(canvas);
  } catch (error) {
    console.error(error);
    showBootError(
      "The 3D scene could not start.",
      "This browser could not create a WebGL context. The simulation needs WebGL; try a current browser with hardware acceleration enabled.",
    );
    return;
  }

  const chart = new TemperatureChart(requireElement<HTMLCanvasElement>("chart"), timeline);
  const hud = new Hud(chart);
  const terminal = new AttackerTerminal();
  const live = requireElement("live-region");
  const alarmWash = requireElement("alarm-wash");
  const restart = requireElement<HTMLButtonElement>("restart");
  const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  let reducedMotion = motionQuery.matches;

  motionQuery.addEventListener("change", (event) => {
    reducedMotion = event.matches;
  });

  restart.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: reducedMotion ? "auto" : "smooth" });
  });

  const pointerTarget = { x: 0, y: 0 };
  const pointer = { x: 0, y: 0 };
  window.addEventListener(
    "pointermove",
    (event) => {
      pointerTarget.x = (event.clientX / window.innerWidth) * 2 - 1;
      pointerTarget.y = -((event.clientY / window.innerHeight) * 2 - 1);
    },
    { passive: true },
  );

  const scrollStageFloat = (): number => {
    const viewport = Math.max(1, window.innerHeight);
    const progress = window.scrollY / (STAGE_COUNT * viewport);
    return stageFloatForProgress(progress);
  };

  let displayStageFloat = scrollStageFloat();
  let previousStageFloat = displayStageFloat;
  let elapsed = 0;
  let lastTimestamp = 0;
  let firstFrameTime: number | null = null;
  let bootHidden = false;
  let announcedStage = -1;
  let announcedClassification: Classification | null = null;

  const announce = (stageIndex: number, classification: Classification): void => {
    if (stageIndex === announcedStage && classification === announcedClassification) return;
    announcedStage = stageIndex;
    announcedClassification = classification;
    const stage = STAGES[stageIndex];
    live.textContent = `Stage ${stageIndex + 1} of ${STAGE_COUNT}, ${
      stage.label
    }. Battery classified ${classificationLabel(classification)}.`;
  };

  const frame = (timestamp: number): void => {
    const dt = lastTimestamp === 0 ? 0 : Math.min(0.05, (timestamp - lastTimestamp) / 1000);
    lastTimestamp = timestamp;
    elapsed += dt;

    const targetStageFloat = scrollStageFloat();
    if (reducedMotion) {
      displayStageFloat = targetStageFloat;
    } else {
      const blend = 1 - Math.exp(-dt * 7);
      displayStageFloat += (targetStageFloat - displayStageFloat) * blend;
      if (Math.abs(targetStageFloat - displayStageFloat) < 0.0005) {
        displayStageFloat = targetStageFloat;
      }
    }

    const scrollVelocity = dt > 0 ? (displayStageFloat - previousStageFloat) / dt : 0;
    previousStageFloat = displayStageFloat;

    const simTime = simTimeForStageFloat(displayStageFloat);
    const sample = timeline.sampleAt(simTime);

    const pointerBlend = reducedMotion ? 1 : Math.min(1, dt * 6);
    pointer.x += (pointerTarget.x - pointer.x) * pointerBlend;
    pointer.y += (pointerTarget.y - pointer.y) * pointerBlend;

    world.render({
      sample,
      stageFloat: displayStageFloat,
      elapsed,
      dt,
      pointer,
      scrollVelocity: reducedMotion ? 0 : scrollVelocity,
      reducedMotion,
    });
    hud.update(sample);
    terminal.update(sample);
    announce(sample.stageIndex, sample.classification);

    alarmWash.classList.toggle("is-active", sample.alarm);

    if (!bootHidden) {
      if (firstFrameTime === null) firstFrameTime = timestamp;
      if (timestamp - firstFrameTime > 280) {
        bootHidden = true;
        boot.classList.add("is-hidden");
        boot.setAttribute("aria-hidden", "true");
      }
    }

    requestAnimationFrame(frame);
  };

  window.addEventListener(
    "resize",
    () => {
      world.resize();
      chart.resize();
    },
    { passive: true },
  );

  window.addEventListener(
    "pagehide",
    () => {
      world.dispose();
      chart.disconnect();
    },
    { once: true },
  );

  requestAnimationFrame(frame);
}

start();
