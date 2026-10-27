import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import type { Classification } from "../sim/classifier";
import { COLORS } from "../tokens";

export interface TwoWheelerInput {
  speedKmh: number;
  classification: Classification;
  alarm: boolean;
  rest: boolean;
  scrollVelocity: number;
  elapsed: number;
  dt: number;
  reducedMotion: boolean;
}

/** Lightweight electric motorcycle model built from the same scene primitives. */
export class TwoWheelerRig {
  readonly group = new THREE.Group();
  private readonly wheels: THREE.Group[] = [];
  private readonly accent: THREE.MeshStandardMaterial;
  private readonly headlight: THREE.MeshStandardMaterial;
  private readonly tailLight: THREE.MeshStandardMaterial;
  private readonly warningLight: THREE.MeshStandardMaterial;

  constructor() {
    this.group.scale.setScalar(1.4);
    const paint = new THREE.MeshStandardMaterial({ color: COLORS.rule, roughness: 0.78, metalness: 0.06 });
    const trim = new THREE.MeshStandardMaterial({ color: COLORS.graphite, roughness: 0.62, metalness: 0.2 });
    const glass = new THREE.MeshStandardMaterial({ color: COLORS.glass, roughness: 0.14, metalness: 0.4 });
    this.accent = new THREE.MeshStandardMaterial({
      color: COLORS.inkSoft,
      roughness: 0.8,
      metalness: 0.04,
    });
    this.headlight = new THREE.MeshStandardMaterial({ color: COLORS.benchDeep, roughness: 0.8 });
    this.tailLight = new THREE.MeshStandardMaterial({ color: COLORS.inkSoft, roughness: 0.82 });
    this.warningLight = new THREE.MeshStandardMaterial({ color: COLORS.inkSoft, roughness: 0.82 });

    const addBar = (from: THREE.Vector3, to: THREE.Vector3, radius: number, material: THREE.Material) => {
      const direction = to.clone().sub(from);
      const bar = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, direction.length(), 8), material);
      bar.position.copy(from).add(to).multiplyScalar(0.5);
      bar.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());
      this.group.add(bar);
    };

    const rear = new THREE.Vector3(-1.02, 0.43, 0);
    const front = new THREE.Vector3(1.02, 0.43, 0);
    const crank = new THREE.Vector3(-0.05, 0.44, 0);
    const steering = new THREE.Vector3(0.52, 0.85, 0);
    const seatPost = new THREE.Vector3(-0.57, 0.94, 0);
    addBar(rear, crank, 0.045, trim);
    addBar(crank, steering, 0.045, trim);
    addBar(steering, rear, 0.045, trim);
    addBar(rear, seatPost, 0.045, trim);
    addBar(seatPost, crank, 0.045, trim);
    addBar(steering, front, 0.035, trim);
    addBar(new THREE.Vector3(0.46, 0.9, 0), new THREE.Vector3(0.83, 0.9, 0), 0.025, trim);

    const battery = new THREE.Mesh(new RoundedBoxGeometry(0.58, 0.46, 0.5, 4, 0.08), trim);
    battery.position.set(-0.02, 0.74, 0);
    this.group.add(battery);
    const fairing = new THREE.Mesh(new RoundedBoxGeometry(0.73, 0.39, 0.58, 5, 0.12), paint);
    fairing.position.set(0.41, 1.02, 0);
    fairing.rotation.z = -0.1;
    this.group.add(fairing);
    const windscreen = new THREE.Mesh(new RoundedBoxGeometry(0.31, 0.27, 0.44, 4, 0.08), glass);
    windscreen.position.set(0.58, 1.31, 0);
    windscreen.rotation.z = -0.24;
    this.group.add(windscreen);
    const seat = new THREE.Mesh(new RoundedBoxGeometry(0.67, 0.13, 0.46, 4, 0.06), trim);
    seat.position.set(-0.54, 1.06, 0);
    this.group.add(seat);
    const rearCowl = new THREE.Mesh(new RoundedBoxGeometry(0.44, 0.24, 0.49, 4, 0.08), paint);
    rearCowl.position.set(-0.91, 0.91, 0);
    rearCowl.rotation.z = 0.24;
    this.group.add(rearCowl);

    const batteryMark = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.035, 0.014), this.accent);
    batteryMark.position.set(-0.02, 0.77, 0.257);
    this.group.add(batteryMark);
    const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.13, 16, 12), this.headlight);
    lamp.scale.set(0.7, 0.55, 1.15);
    lamp.position.set(0.91, 1.01, 0);
    this.group.add(lamp);
    const rearLamp = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.09, 0.36), this.tailLight);
    rearLamp.position.set(-1.15, 0.9, 0);
    this.group.add(rearLamp);
    const warning = new THREE.Mesh(new RoundedBoxGeometry(0.2, 0.035, 0.12, 2, 0.015), this.warningLight);
    warning.position.set(-0.2, 1.51, 0);
    this.group.add(warning);

    const tireMaterial = new THREE.MeshStandardMaterial({ color: COLORS.tire, roughness: 0.92 });
    const rimMaterial = new THREE.MeshStandardMaterial({ color: COLORS.rule, roughness: 0.34, metalness: 0.72 });
    const tireGeometry = new THREE.CylinderGeometry(0.38, 0.38, 0.18, 28);
    const rimGeometry = new THREE.CylinderGeometry(0.25, 0.25, 0.2, 24);
    const hubGeometry = new THREE.CylinderGeometry(0.07, 0.07, 0.22, 16);
    for (const x of [-1.02, 1.02]) {
      const pivot = new THREE.Group();
      pivot.position.set(x, 0.43, 0);
      for (const [geometry, material] of [[tireGeometry, tireMaterial], [rimGeometry, rimMaterial], [hubGeometry, trim]] as const) {
        const wheelPart = new THREE.Mesh(geometry, material);
        wheelPart.rotation.x = Math.PI / 2;
        wheelPart.castShadow = true;
        pivot.add(wheelPart);
      }
      this.wheels.push(pivot);
      this.group.add(pivot);
    }

    this.group.traverse((object) => {
      if (object instanceof THREE.Mesh) {
        object.castShadow = true;
        object.receiveShadow = true;
      }
    });
  }

  update(input: TwoWheelerInput): void {
    const motionFactor = input.reducedMotion || input.rest ? 0 : 1;
    const wheelSpin = Math.min(1.6, Math.abs(input.speedKmh) / 90)
      * Math.min(1.5, Math.abs(input.scrollVelocity)) * input.dt * 7 * motionFactor;
    for (const wheel of this.wheels) wheel.rotation.z -= wheelSpin;
  }
}
