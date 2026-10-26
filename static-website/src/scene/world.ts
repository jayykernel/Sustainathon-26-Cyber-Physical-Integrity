import * as THREE from "three";
import { SIMULATION } from "../config";
import type { TimelineSample } from "../sim/timeline";
import { COLORS, colorForClassification } from "../tokens";
import { BatteryRig } from "./battery";
import { CarRig } from "./car";
import { createEnvironment } from "./environment";
import { HackerNode } from "./hacker";

export interface PointerState {
  x: number;
  y: number;
}

export interface SceneFrame {
  sample: TimelineSample;
  stageFloat: number;
  elapsed: number;
  dt: number;
  pointer: PointerState;
  scrollVelocity: number;
  reducedMotion: boolean;
}

interface CameraKeyframe {
  position: THREE.Vector3;
  target: THREE.Vector3;
  fov: number;
}

const KEYFRAMES: readonly CameraKeyframe[] = [
  {
    position: new THREE.Vector3(4.2, 2.3, 7.1),
    target: new THREE.Vector3(0.05, 0.78, 0),
    fov: 38,
  },
  {
    position: new THREE.Vector3(5.3, 2.2, 6.1),
    target: new THREE.Vector3(-0.1, 0.82, 0),
    fov: 40,
  },
  {
    position: new THREE.Vector3(3.4, 1.95, 7.5),
    target: new THREE.Vector3(0, 0.86, 0),
    fov: 41,
  },
  {
    position: new THREE.Vector3(1.2, -1.05, 5.4),
    target: new THREE.Vector3(0, 0.18, 0.05),
    fov: 42,
  },
  {
    position: new THREE.Vector3(-4.3, 2.35, 6.2),
    target: new THREE.Vector3(0, 0.95, 0),
    fov: 39,
  },
  {
    position: new THREE.Vector3(4.9, 2.6, 6.6),
    target: new THREE.Vector3(-0.65, 0.9, 0),
    fov: 38,
  },
  {
    position: new THREE.Vector3(0.2, 1.9, 9.6),
    target: new THREE.Vector3(0, 0.7, 0),
    fov: 35,
  },
];

function smoothstep(value: number): number {
  const bounded = Math.min(1, Math.max(0, value));
  return bounded * bounded * (3 - 2 * bounded);
}

/** Owns the renderer, stage lighting, and camera choreography. */
export class SimulationWorld {
  private readonly scene = new THREE.Scene();
  private readonly camera: THREE.PerspectiveCamera;
  private readonly renderer: THREE.WebGLRenderer;
  private readonly car = new CarRig();
  private readonly battery = new BatteryRig();
  private readonly hacker = new HackerNode();
  private readonly environment = createEnvironment();
  private readonly desiredPosition = new THREE.Vector3();
  private readonly desiredTarget = new THREE.Vector3();
  private readonly tone = new THREE.Color(COLORS.nominal);
  private pointerX = 0;
  private pointerY = 0;

  constructor(canvas: HTMLCanvasElement) {
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: false,
      powerPreference: "high-performance",
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setSize(window.innerWidth, window.innerHeight, false);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    this.scene.background = new THREE.Color(COLORS.bench);
    this.scene.fog = new THREE.Fog(COLORS.bench, 22, 42);

    this.camera = new THREE.PerspectiveCamera(
      38,
      window.innerWidth / Math.max(1, window.innerHeight),
      0.1,
      90,
    );
    this.camera.position.copy(KEYFRAMES[0].position);
    this.camera.lookAt(KEYFRAMES[0].target);

    this.buildLights();

    this.scene.add(this.environment.group);
    this.scene.add(this.car.group);
    this.scene.add(this.battery.group);
    this.scene.add(this.hacker.group);

    this.scene.traverse((object) => {
      if (object instanceof THREE.Mesh) {
        object.castShadow = true;
        object.receiveShadow = true;
      }
    });

    this.resize();
  }

  private buildLights(): void {
    const hemisphere = new THREE.HemisphereLight(COLORS.sheet, COLORS.benchDeep, 1.55);
    this.scene.add(hemisphere);

    const key = new THREE.DirectionalLight(0xffffff, 2.5);
    key.position.set(5.5, 8.5, 5.5);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    key.shadow.camera.left = -7;
    key.shadow.camera.right = 7;
    key.shadow.camera.top = 7;
    key.shadow.camera.bottom = -7;
    key.shadow.camera.near = 0.5;
    key.shadow.camera.far = 24;
    key.shadow.bias = -0.0008;
    this.scene.add(key);

    const fill = new THREE.DirectionalLight(0xe9f0f4, 0.9);
    fill.position.set(-6, 4, -4);
    this.scene.add(fill);

    const rim = new THREE.DirectionalLight(0xffffff, 0.55);
    rim.position.set(0, 3.5, -7);
    this.scene.add(rim);

    const under = new THREE.PointLight(COLORS.sheet, 2.4, 8, 2);
    under.position.set(0, -0.55, 2.4);
    this.scene.add(under);
  }

  resize(): void {
    const width = window.innerWidth;
    const height = Math.max(1, window.innerHeight);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setSize(width, height, false);
  }

  render(frame: SceneFrame): void {
    const { sample, stageFloat, elapsed, dt, pointer, scrollVelocity, reducedMotion } = frame;

    this.updateCamera(stageFloat, pointer, dt, reducedMotion);

    this.tone.set(colorForClassification(sample.classification));
    this.car.update({
      speedKmh: sample.speedKmh,
      classification: sample.classification,
      alarm: sample.alarm,
      rest: sample.t >= SIMULATION.restAt_s,
      scrollVelocity,
      elapsed,
      dt,
      reducedMotion,
    });
    this.battery.update({
      trueTempC: sample.trueTempC,
      reportedTempC: sample.reportedTempC,
      classification: sample.classification,
      alarm: sample.alarm,
      twinActive: sample.twinActive,
      twinResponding: sample.twinResponding,
      elapsed,
      dt,
      reducedMotion,
    });
    this.hacker.update(sample, elapsed, reducedMotion);
    this.environment.update(this.tone, sample.alarm, elapsed, reducedMotion);

    this.renderer.render(this.scene, this.camera);
  }

  private updateCamera(
    stageFloat: number,
    pointer: PointerState,
    dt: number,
    reducedMotion: boolean,
  ): void {
    const bounded = Math.min(KEYFRAMES.length - 1, Math.max(0, stageFloat));
    const index = Math.min(KEYFRAMES.length - 2, Math.floor(bounded));
    const fraction = smoothstep(bounded - index);
    const from = KEYFRAMES[index];
    const to = KEYFRAMES[index + 1];

    this.desiredPosition.lerpVectors(from.position, to.position, fraction);
    this.desiredTarget.lerpVectors(from.target, to.target, fraction);

    const targetX = reducedMotion ? 0 : pointer.x;
    const targetY = reducedMotion ? 0 : pointer.y;
    const pointerBlend = 1 - Math.exp(-dt * 3);
    this.pointerX += (targetX - this.pointerX) * pointerBlend;
    this.pointerY += (targetY - this.pointerY) * pointerBlend;

    this.camera.position.copy(this.desiredPosition);
    this.camera.position.x += this.pointerX * 0.26;
    this.camera.position.y += this.pointerY * 0.14;

    // Leave visual room for the narrative card on the left and the HUD on the
    // right by aiming a little to the left of the car.
    const composition = THREE.MathUtils.clamp((this.camera.aspect - 1.15) * 1.5, 0, 1);
    this.camera.lookAt(
      this.desiredTarget.x - composition,
      this.desiredTarget.y,
      this.desiredTarget.z,
    );

    const fov = from.fov + (to.fov - from.fov) * fraction;
    if (Math.abs(this.camera.fov - fov) > 0.001) {
      this.camera.fov = fov;
      this.camera.updateProjectionMatrix();
    }
  }

  dispose(): void {
    this.scene.traverse((object) => {
      if (
        object instanceof THREE.Mesh ||
        object instanceof THREE.Line ||
        object instanceof THREE.LineSegments
      ) {
        object.geometry.dispose();
        const material = object.material;
        if (Array.isArray(material)) {
          material.forEach((entry) => entry.dispose());
        } else {
          material.dispose();
        }
      }
    });
    this.renderer.dispose();
  }
}
