import * as THREE from "three";
import { CSS2DRenderer } from "three/addons/renderers/CSS2DRenderer.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { TimelineSample } from "../sim/timeline";
import { COLORS } from "../tokens";
import { BatteryRig } from "./battery";
import { CarRig } from "./car";
import { TwoWheelerRig } from "./twoWheeler";
import { createEnvironment } from "./environment";
import { HackerNode } from "./hacker";

export type VehicleType = "car" | "two_wheeler";

export interface SceneFrame {
  sample: TimelineSample;
  stageFloat: number;
  elapsed: number;
  dt: number;
  scrollVelocity: number;
  reducedMotion: boolean;
  vehicleType: VehicleType;
  incidentFocus: number;
}

interface CameraKeyframe {
  position: THREE.Vector3;
  target: THREE.Vector3;
  fov: number;
}

const KEYFRAMES: readonly CameraKeyframe[] = [
  {
    position: new THREE.Vector3(5.0, 2.7, 9.0),
    target: new THREE.Vector3(0.05, 0.78, 0),
    fov: 41,
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
  private readonly vehicleStage = new THREE.Group();
  private readonly camera: THREE.PerspectiveCamera;
  private controls!: OrbitControls;
  private readonly renderer: THREE.WebGLRenderer;
  private readonly labelRenderer = new CSS2DRenderer();
  private readonly car = new CarRig();
  private readonly twoWheeler = new TwoWheelerRig();
  private readonly battery = new BatteryRig();
  private readonly hacker = new HackerNode();
  private readonly environment = createEnvironment();
  private readonly desiredPosition = new THREE.Vector3();
  private readonly desiredTarget = new THREE.Vector3();
  private readonly focusPosition = new THREE.Vector3();
  private readonly focusTarget = new THREE.Vector3(0, 0.85, 0);
  private readonly renderTarget = new THREE.Vector3();
  private readonly cameraPathPosition = new THREE.Vector3();
  private readonly cameraPathTarget = new THREE.Vector3();
  private readonly orbitStartPosition = new THREE.Vector3();
  private readonly orbitStartTarget = new THREE.Vector3();
  private orbitActive = false;
  private orbitUntil = 0;
  private orbitReleaseElapsed = -1;

  constructor(canvas: HTMLCanvasElement) {
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: false,
      powerPreference: "high-performance",
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setSize(window.innerWidth, window.innerHeight, false);
    this.labelRenderer.setSize(window.innerWidth, window.innerHeight);
    this.labelRenderer.domElement.className = "scene-label-layer";
    this.labelRenderer.domElement.setAttribute("aria-hidden", "true");
    canvas.insertAdjacentElement("afterend", this.labelRenderer.domElement);
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
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.075;
    this.controls.enablePan = false;
    this.controls.enableZoom = false;
    this.controls.rotateSpeed = 0.65;
    this.controls.autoRotate = false;
    this.controls.addEventListener("start", () => {
      this.orbitActive = true;
      this.orbitUntil = Number.POSITIVE_INFINITY;
      this.orbitReleaseElapsed = -1;
    });
    this.controls.addEventListener("end", () => {
      this.orbitUntil = performance.now() + 2200;
    });

    this.buildLights();

    this.vehicleStage.position.x = 1.8;
    this.vehicleStage.scale.setScalar(0.82);
    this.scene.add(this.vehicleStage);
    this.vehicleStage.add(this.environment.group);
    this.vehicleStage.add(this.car.group);
    this.twoWheeler.group.visible = false;
    this.vehicleStage.add(this.twoWheeler.group);
    this.vehicleStage.add(this.battery.group);
    this.vehicleStage.add(this.hacker.group);

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

    const key = new THREE.DirectionalLight(COLORS.sheet, 2.5);
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

    const fill = new THREE.DirectionalLight(COLORS.benchDeep, 0.9);
    fill.position.set(-6, 4, -4);
    this.scene.add(fill);

    const rim = new THREE.DirectionalLight(COLORS.sheet, 0.55);
    rim.position.set(0, 3.5, -7);
    this.scene.add(rim);

  }

  resize(): void {
    const width = window.innerWidth;
    const height = Math.max(1, window.innerHeight);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setSize(width, height, false);
    this.labelRenderer.setSize(width, height);
  }

  render(frame: SceneFrame): void {
    const { sample, stageFloat, elapsed, dt, scrollVelocity, reducedMotion, vehicleType, incidentFocus } = frame;

    this.car.group.visible = vehicleType === "car";
    this.twoWheeler.group.visible = vehicleType === "two_wheeler";
    const now = performance.now();
    if (this.orbitActive && now < this.orbitUntil) {
      this.controls.update();
    } else {
      if (this.orbitActive) {
        this.orbitActive = false;
        this.orbitReleaseElapsed = 0;
        this.orbitStartPosition.copy(this.camera.position);
        this.orbitStartTarget.copy(this.controls.target);
      }
      this.updateCamera(stageFloat, dt, vehicleType, incidentFocus);
    }

    this.car.update({
      speedKmh: sample.speedKmh,
      classification: sample.classification,
      alarm: sample.alarm,
      rest: sample.t >= (sample.duration_s ?? 3600) - 60,
      scrollVelocity,
      elapsed,
      dt,
      reducedMotion,
    });
    this.twoWheeler.update({
      speedKmh: sample.speedKmh,
      classification: sample.classification,
      alarm: sample.alarm,
      rest: sample.t >= (sample.duration_s ?? 3600) - 60,
      scrollVelocity,
      elapsed,
      dt,
      reducedMotion,
    });
    this.battery.update({
      trueTempC: sample.trueTempC,
      reportedTempC: sample.reportedTempC,
      channel: sample.channel ?? "A",
      classification: sample.classification,
      alarm: sample.alarm,
      twinActive: sample.twinActive,
      twinProtecting: sample.twinProtecting,
      elapsed,
      dt,
      reducedMotion,
    });
    this.environment.setState(sample.classification);
    this.hacker.update(sample, elapsed, reducedMotion);
    this.renderer.render(this.scene, this.camera);
    this.labelRenderer.render(this.scene, this.camera);
  }

  private updateCamera(
    stageFloat: number,
    dt: number,
    vehicleType: VehicleType,
    incidentFocus: number,
  ): void {
    const bounded = Math.min(KEYFRAMES.length - 1, Math.max(0, stageFloat));
    const index = Math.min(KEYFRAMES.length - 2, Math.floor(bounded));
    const fraction = smoothstep(bounded - index);
    const from = KEYFRAMES[index];
    const to = KEYFRAMES[index + 1];

    this.desiredPosition.lerpVectors(from.position, to.position, fraction);
    this.desiredTarget.lerpVectors(from.target, to.target, fraction);

    const focus = THREE.MathUtils.clamp(incidentFocus, 0, 1);
    this.focusPosition.set(3.4, vehicleType === "car" ? 1.95 : 2.05, vehicleType === "car" ? 5.8 : 5.6);
    const focusStrength = this.camera.aspect < 0.8 ? 0.3 : this.camera.aspect < 1.2 ? 0.48 : 0.6;
    this.cameraPathPosition.lerpVectors(this.desiredPosition, this.focusPosition, focus * focusStrength);
    // Move the vehicle opposite the chapter copy so the scroll story keeps a
    // clear editorial column and an unobstructed view of the battery scene.
    const composition = THREE.MathUtils.clamp((this.camera.aspect - 1.15) * 1.5, 0, 1);
    this.renderTarget.lerpVectors(this.desiredTarget, this.focusTarget, focus);
    const chapterIndex = Math.min(6, Math.floor(stageFloat));
    const textOnRight = chapterIndex > 0 && chapterIndex % 2 === 1;
    const sceneOffset = (textOnRight ? 1 : -1) * composition * 1.7;
    this.cameraPathTarget.set(this.renderTarget.x + sceneOffset, this.renderTarget.y, this.renderTarget.z);
    if (this.orbitReleaseElapsed >= 0) {
      this.orbitReleaseElapsed += dt;
      const blend = smoothstep(Math.min(1, this.orbitReleaseElapsed / 1.5));
      this.camera.position.lerpVectors(this.orbitStartPosition, this.cameraPathPosition, blend);
      this.renderTarget.lerpVectors(this.orbitStartTarget, this.cameraPathTarget, blend);
      this.camera.lookAt(this.renderTarget);
      if (blend >= 1) this.orbitReleaseElapsed = -1;
    } else {
      this.camera.position.copy(this.cameraPathPosition);
      this.camera.lookAt(this.cameraPathTarget);
    }
    this.controls.target.copy(this.cameraPathTarget);
    if (this.orbitReleaseElapsed < 0) this.controls.update();

    const baseFov = from.fov + (to.fov - from.fov) * fraction;
    const focusFov = this.camera.aspect < 0.8 ? 2.5 : this.camera.aspect < 1.2 ? 4 : vehicleType === "car" ? 6 : 5;
    const fov = baseFov - focus * focusFov;
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
    this.controls.dispose();
    this.labelRenderer.domElement.remove();
  }
}
