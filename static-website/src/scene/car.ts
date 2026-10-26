import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import type { Classification } from "../sim/classifier";
import { COLORS, colorForClassification } from "../tokens";

export interface CarInput {
  speedKmh: number;
  classification: Classification;
  alarm: boolean;
  rest: boolean;
  /** Continuous stage progress per second. Drives the wheels while scrolling. */
  scrollVelocity: number;
  elapsed: number;
  dt: number;
  reducedMotion: boolean;
}

/**
 * A deliberately simple, readable electric car assembled from primitives.
 * The silhouette, wheels, and light bars carry the state; there is no imported
 * model and no external asset.
 */
export class CarRig {
  readonly group = new THREE.Group();

  private readonly bodyGroup = new THREE.Group();
  private readonly wheels: THREE.Group[] = [];
  private readonly accentMaterial: THREE.MeshStandardMaterial;
  private readonly headlightMaterial: THREE.MeshStandardMaterial;
  private readonly tailMaterial: THREE.MeshStandardMaterial;
  private readonly beaconMaterial: THREE.MeshStandardMaterial;
  private readonly cabinLight: THREE.PointLight;
  private readonly accentLight: THREE.PointLight;
  private readonly targetTone = new THREE.Color(COLORS.nominal);

  constructor() {
    this.group.add(this.bodyGroup);

    const paint = new THREE.MeshStandardMaterial({
      color: "#D8DEE2",
      roughness: 0.34,
      metalness: 0.5,
    });
    const darkTrim = new THREE.MeshStandardMaterial({
      color: COLORS.graphite,
      roughness: 0.62,
      metalness: 0.2,
    });
    const glass = new THREE.MeshStandardMaterial({
      color: COLORS.glass,
      roughness: 0.12,
      metalness: 0.45,
    });

    this.accentMaterial = new THREE.MeshStandardMaterial({
      color: COLORS.nominal,
      emissive: COLORS.nominal,
      emissiveIntensity: 0.55,
      roughness: 0.35,
      metalness: 0.1,
    });
    this.headlightMaterial = new THREE.MeshStandardMaterial({
      color: "#FFF8E4",
      emissive: "#FFF1CC",
      emissiveIntensity: 1.5,
      roughness: 0.3,
    });
    this.tailMaterial = new THREE.MeshStandardMaterial({
      color: COLORS.hazard,
      emissive: COLORS.hazard,
      emissiveIntensity: 0.55,
      roughness: 0.4,
    });
    this.beaconMaterial = new THREE.MeshStandardMaterial({
      color: COLORS.hazard,
      emissive: COLORS.hazard,
      emissiveIntensity: 0.05,
      roughness: 0.4,
    });

    const body = new THREE.Mesh(new RoundedBoxGeometry(4.08, 0.58, 1.86, 4, 0.14), paint);
    body.position.y = 0.64;
    this.bodyGroup.add(body);

    const skirt = new THREE.Mesh(new RoundedBoxGeometry(3.7, 0.16, 1.9, 3, 0.05), darkTrim);
    skirt.position.y = 0.4;
    this.bodyGroup.add(skirt);

    const belt = new THREE.Mesh(new RoundedBoxGeometry(2.12, 0.26, 1.72, 3, 0.09), paint);
    belt.position.set(-0.1, 1.02, 0);
    this.bodyGroup.add(belt);

    const greenhouse = new THREE.Mesh(new RoundedBoxGeometry(2.0, 0.4, 1.62, 3, 0.12), glass);
    greenhouse.position.set(-0.12, 1.3, 0);
    this.bodyGroup.add(greenhouse);

    const roof = new THREE.Mesh(new RoundedBoxGeometry(1.7, 0.13, 1.48, 3, 0.06), paint);
    roof.position.set(-0.18, 1.52, 0);
    this.bodyGroup.add(roof);

    const hood = new THREE.Mesh(new RoundedBoxGeometry(1.05, 0.1, 1.7, 3, 0.05), paint);
    hood.position.set(1.52, 0.96, 0);
    this.bodyGroup.add(hood);

    const mirrorGeometry = new THREE.BoxGeometry(0.15, 0.07, 0.09);
    for (const side of [-1, 1]) {
      const mirror = new THREE.Mesh(mirrorGeometry, paint);
      mirror.position.set(0.58, 1.15, side * 0.98);
      mirror.castShadow = true;
      this.bodyGroup.add(mirror);
    }

    const accentBar = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.035, 1.2), this.accentMaterial);
    accentBar.position.set(2.055, 0.67, 0);
    this.bodyGroup.add(accentBar);

    for (const side of [-1, 1]) {
      const stripe = new THREE.Mesh(new THREE.BoxGeometry(2.9, 0.045, 0.014), this.accentMaterial);
      stripe.position.set(-0.08, 0.8, side * 0.935);
      this.bodyGroup.add(stripe);
    }

    const headlightGeometry = new THREE.BoxGeometry(0.05, 0.1, 0.36);
    for (const side of [-1, 1]) {
      const light = new THREE.Mesh(headlightGeometry, this.headlightMaterial);
      light.position.set(2.04, 0.79, side * 0.55);
      this.bodyGroup.add(light);
    }

    const tailBar = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.055, 1.32), this.tailMaterial);
    tailBar.position.set(-2.05, 0.79, 0);
    this.bodyGroup.add(tailBar);

    const beacon = new THREE.Mesh(
      new RoundedBoxGeometry(0.62, 0.06, 0.2, 2, 0.03),
      this.beaconMaterial,
    );
    beacon.position.set(0.3, 1.6, 0);
    this.bodyGroup.add(beacon);

    this.cabinLight = new THREE.PointLight(COLORS.hazard, 0, 3.2, 2);
    this.cabinLight.position.set(-0.1, 1.18, 0);
    this.bodyGroup.add(this.cabinLight);

    this.accentLight = new THREE.PointLight(COLORS.nominal, 0.5, 3.4, 2);
    this.accentLight.position.set(0, 0.2, 0);
    this.group.add(this.accentLight);

    const tireMaterial = new THREE.MeshStandardMaterial({
      color: COLORS.tire,
      roughness: 0.9,
      metalness: 0.05,
    });
    const hubMaterial = new THREE.MeshStandardMaterial({
      color: "#AEB8BE",
      roughness: 0.35,
      metalness: 0.7,
    });
    const tireGeometry = new THREE.CylinderGeometry(0.37, 0.37, 0.24, 24);
    const hubGeometry = new THREE.CylinderGeometry(0.19, 0.19, 0.26, 20);

    for (const x of [-1.31, 1.31]) {
      for (const z of [-0.84, 0.84]) {
        const pivot = new THREE.Group();
        pivot.position.set(x, 0.37, z);

        const tire = new THREE.Mesh(tireGeometry, tireMaterial);
        tire.rotation.x = Math.PI / 2;
        tire.castShadow = true;
        pivot.add(tire);

        const hub = new THREE.Mesh(hubGeometry, hubMaterial);
        hub.rotation.x = Math.PI / 2;
        pivot.add(hub);

        this.wheels.push(pivot);
        this.group.add(pivot);
      }
    }

    this.group.traverse((object) => {
      if (object instanceof THREE.Mesh) {
        object.castShadow = true;
        object.receiveShadow = true;
      }
    });
  }

  update(input: CarInput): void {
    this.targetTone.set(colorForClassification(input.classification));
    const blend = input.reducedMotion ? 1 : 1 - Math.exp(-input.dt * 5);
    this.accentMaterial.color.lerp(this.targetTone, blend);
    this.accentMaterial.emissive.lerp(this.targetTone, blend);
    this.accentLight.color.lerp(this.targetTone, blend);
    this.accentLight.intensity = input.rest ? 0.18 : input.alarm ? 1.1 : 0.6;

    const speedFactor = Math.min(1.6, Math.abs(input.speedKmh) / 90);
    const scrollFactor = input.rest ? 0 : Math.min(1.5, Math.abs(input.scrollVelocity));
    const spin = speedFactor * scrollFactor * input.dt * 7;
    for (const wheel of this.wheels) {
      wheel.rotation.z -= spin;
    }

    const pulse = input.reducedMotion ? 1 : 0.5 + 0.5 * Math.sin(input.elapsed * 8);
    this.beaconMaterial.emissiveIntensity = input.alarm && !input.rest ? 0.5 + pulse * 2.2 : 0.05;
    this.cabinLight.intensity = input.alarm && !input.rest ? (input.reducedMotion ? 1.6 : 0.8 + pulse * 1.5) : 0;
    this.headlightMaterial.emissiveIntensity = input.rest ? 0.12 : 1.5;
    this.tailMaterial.emissiveIntensity = input.alarm && !input.rest ? 0.7 + pulse * 1.3 : input.rest ? 0.08 : 0.55;

    const bob =
      input.reducedMotion || input.rest
        ? 0
        : Math.sin(input.elapsed * 7.5) * 0.004 * Math.min(1, speedFactor);
    this.bodyGroup.position.y = bob - (input.rest ? 0.012 : 0);
  }
}
