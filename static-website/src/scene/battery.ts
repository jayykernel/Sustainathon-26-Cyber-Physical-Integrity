import * as THREE from "three";
import type { Classification } from "../sim/classifier";
import { COLORS } from "../tokens";

export interface BatteryInput {
  trueTempC: number;
  reportedTempC: number;
  classification: Classification;
  alarm: boolean;
  twinActive: boolean;
  twinResponding: boolean;
  elapsed: number;
  dt: number;
  reducedMotion: boolean;
}

const NOMINAL = new THREE.Color(COLORS.nominal);
const CAUTION = new THREE.Color(COLORS.caution);
const HAZARD = new THREE.Color(COLORS.hazard);

function temperatureColor(tempC: number, target: THREE.Color): void {
  const fraction = Math.min(1, Math.max(0, (tempC - 35) / 20));
  if (fraction < 0.65) {
    target.copy(NOMINAL).lerp(CAUTION, fraction / 0.65);
  } else {
    target.copy(CAUTION).lerp(HAZARD, (fraction - 0.65) / 0.35);
  }
}

/**
 * The floor-mounted pack: ten cells, a tamper pod, and a hovering wireframe
 * ghost that represents the one-RC digital twin once it is engaged.
 */
export class BatteryRig {
  readonly group = new THREE.Group();

  private readonly cellMaterials: THREE.MeshStandardMaterial[] = [];
  private readonly twinGroup = new THREE.Group();
  private readonly twinMaterials: (THREE.Material & { opacity: number })[] = [];
  private readonly twinBaseOpacity: number[] = [];
  private readonly sensorMaterial: THREE.MeshStandardMaterial;
  private readonly sensorLink: THREE.Line;
  private readonly underLight: THREE.PointLight;
  private readonly scratch = new THREE.Color();
  private readonly twinTargetScale = new THREE.Vector3(1, 1, 1);

  constructor() {
    const frameMaterial = new THREE.MeshStandardMaterial({
      color: COLORS.graphite,
      roughness: 0.5,
      metalness: 0.55,
    });

    const railGeometryX = new THREE.BoxGeometry(2.9, 0.12, 0.07);
    const railGeometryZ = new THREE.BoxGeometry(0.07, 0.12, 1.45);
    for (const side of [-1, 1]) {
      const sideRail = new THREE.Mesh(railGeometryX, frameMaterial);
      sideRail.position.set(0, 0.22, side * 0.72);
      this.group.add(sideRail);

      const endRail = new THREE.Mesh(railGeometryZ, frameMaterial);
      endRail.position.set(side * 1.42, 0.22, 0);
      this.group.add(endRail);
    }

    const crossBar = new THREE.Mesh(new THREE.BoxGeometry(2.86, 0.07, 0.05), frameMaterial);
    crossBar.position.set(0, 0.22, 0);
    this.group.add(crossBar);

    const cellGeometry = new THREE.CylinderGeometry(0.115, 0.115, 0.3, 18);
    for (let index = 0; index < 10; index += 1) {
      const row = index < 5 ? -1 : 1;
      const column = index % 5;
      const material = new THREE.MeshStandardMaterial({
        color: COLORS.nominal,
        emissive: COLORS.nominal,
        emissiveIntensity: 0.35,
        roughness: 0.42,
        metalness: 0.25,
      });
      const cell = new THREE.Mesh(cellGeometry, material);
      cell.position.set(-1.08 + column * 0.54, 0.22, row * 0.34);
      cell.castShadow = true;
      this.cellMaterials.push(material);
      this.group.add(cell);
    }

    this.sensorMaterial = new THREE.MeshStandardMaterial({
      color: COLORS.hazard,
      emissive: COLORS.hazard,
      emissiveIntensity: 0.15,
      roughness: 0.35,
      metalness: 0.3,
    });
    const sensorPod = new THREE.Mesh(
      new THREE.BoxGeometry(0.16, 0.1, 0.24),
      this.sensorMaterial,
    );
    sensorPod.position.set(1.52, 0.26, 0);
    this.group.add(sensorPod);

    const linkGeometry = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(1.52, 0.3, 0),
      new THREE.Vector3(0.5, 0.54, 0.12),
    ]);
    this.sensorLink = new THREE.Line(
      linkGeometry,
      new THREE.LineBasicMaterial({ color: COLORS.hazard, transparent: true, opacity: 0.55 }),
    );
    this.sensorLink.visible = false;
    this.group.add(this.sensorLink);

    this.underLight = new THREE.PointLight(COLORS.hazard, 0, 3, 2);
    this.underLight.position.set(0, -0.2, 0.9);
    this.group.add(this.underLight);

    this.buildTwin();
  }

  private buildTwin(): void {
    this.twinGroup.position.set(0, 2.02, 0);
    this.twinGroup.visible = false;

    const outline = new THREE.EdgesGeometry(new THREE.BoxGeometry(2.78, 0.56, 1.5));
    const outlineMaterial = new THREE.LineBasicMaterial({
      color: COLORS.protected,
      transparent: true,
      opacity: 0.55,
    });
    this.twinGroup.add(new THREE.LineSegments(outline, outlineMaterial));
    this.twinMaterials.push(outlineMaterial);
    this.twinBaseOpacity.push(0.55);

    const plate = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.BoxGeometry(2.6, 0.03, 1.34)),
      new THREE.LineBasicMaterial({ color: COLORS.protected, transparent: true, opacity: 0.3 }),
    );
    plate.position.y = -0.42;
    this.twinGroup.add(plate);
    this.twinMaterials.push(plate.material as THREE.LineBasicMaterial);
    this.twinBaseOpacity.push(0.3);

    const cellGeometry = new THREE.CylinderGeometry(0.115, 0.115, 0.3, 10);
    for (let index = 0; index < 10; index += 1) {
      const row = index < 5 ? -1 : 1;
      const column = index % 5;
      const material = new THREE.MeshBasicMaterial({
        color: COLORS.protected,
        wireframe: true,
        transparent: true,
        opacity: 0.42,
      });
      const cell = new THREE.Mesh(cellGeometry, material);
      cell.position.set(-1.08 + column * 0.54, 0, row * 0.34);
      this.twinGroup.add(cell);
      this.twinMaterials.push(material);
      this.twinBaseOpacity.push(0.42);
    }

    const halo = new THREE.Mesh(
      new THREE.TorusGeometry(1.85, 0.006, 4, 96),
      new THREE.MeshBasicMaterial({
        color: COLORS.protected,
        transparent: true,
        opacity: 0.4,
      }),
    );
    halo.rotation.x = -Math.PI / 2;
    halo.position.y = -0.44;
    this.twinGroup.add(halo);
    this.twinMaterials.push(halo.material as THREE.MeshBasicMaterial);
    this.twinBaseOpacity.push(0.4);

    this.group.add(this.twinGroup);
  }

  update(input: BatteryInput): void {
    const flicker = input.reducedMotion
      ? 0
      : input.alarm
        ? 0.55 * Math.sin(input.elapsed * 2.6)
        : 0;

    for (let index = 0; index < this.cellMaterials.length; index += 1) {
      const material = this.cellMaterials[index];
      const gradient = (index - 4.5) * 0.24;
      const jitter = input.reducedMotion ? 0 : Math.sin(input.elapsed * 1.7 + index * 0.8) * 0.12;
      temperatureColor(input.trueTempC + gradient + jitter + flicker * (index % 3 === 0 ? 1 : 0.4), this.scratch);
      material.color.copy(this.scratch);
      material.emissive.copy(this.scratch);
      material.emissiveIntensity = input.alarm ? 0.55 : 0.32;
    }

    const attack = input.classification !== "safe";
    const sensorPulse = input.reducedMotion ? 1 : 0.55 + 0.45 * Math.sin(input.elapsed * 5.2);
    this.sensorMaterial.emissiveIntensity = attack ? 0.7 + sensorPulse * 1.6 : 0.12;
    this.sensorLink.visible = attack;
    this.underLight.intensity = input.alarm ? 0.9 + sensorPulse * 0.5 : 0.25;

    this.twinGroup.visible = input.twinActive;
    if (input.twinActive) {
      this.twinGroup.scale.lerp(
        this.twinTargetScale,
        input.reducedMotion ? 1 : 1 - Math.exp(-input.dt * 4),
      );
      if (!input.reducedMotion) {
        this.twinGroup.position.y = 2.02 + Math.sin(input.elapsed * 1.3) * 0.05;
        this.twinGroup.rotation.y += input.dt * (input.twinResponding ? 0.35 : 0.08);
      }
      const respondFactor = input.twinResponding ? 1 : 0.5;
      for (let index = 0; index < this.twinMaterials.length; index += 1) {
        const material = this.twinMaterials[index];
        material.opacity = this.twinBaseOpacity[index] * respondFactor;
      }
    }
  }
}
