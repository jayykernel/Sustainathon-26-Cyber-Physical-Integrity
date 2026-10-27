import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import type { Classification } from "../sim/classifier";
import { COLORS } from "../tokens";

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
 * A Tesla Model 3 inspired electric sedan, assembled from local Three.js
 * geometry. The telemetry effects stay attached to this visual model.
 */
export class CarRig {
  readonly group = new THREE.Group();

  private readonly bodyGroup = new THREE.Group();
  private readonly wheels: THREE.Group[] = [];
  private readonly accentMaterial: THREE.MeshStandardMaterial;
  private readonly headlightMaterial: THREE.MeshStandardMaterial;
  private readonly tailMaterial: THREE.MeshStandardMaterial;
  private readonly beaconMaterial: THREE.MeshStandardMaterial;

  constructor() {
    this.group.add(this.bodyGroup);

    const paint = new THREE.MeshStandardMaterial({
      color: COLORS.inkSoft,
      roughness: 0.78,
      metalness: 0.06,
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
      color: COLORS.inkSoft,
      roughness: 0.8,
      metalness: 0.04,
    });
    this.headlightMaterial = new THREE.MeshStandardMaterial({
      color: COLORS.benchDeep,
      roughness: 0.8,
    });
    this.tailMaterial = new THREE.MeshStandardMaterial({
      color: COLORS.inkSoft,
      roughness: 0.82,
    });
    this.beaconMaterial = new THREE.MeshStandardMaterial({
      color: COLORS.inkSoft,
      roughness: 0.82,
    });

    const silhouette = new THREE.Shape();
    silhouette.moveTo(-2.18, 0.48);
    silhouette.quadraticCurveTo(-2.25, 0.51, -2.21, 0.64);
    silhouette.lineTo(-2.05, 0.82);
    silhouette.quadraticCurveTo(-1.98, 0.9, -1.82, 0.93);
    silhouette.lineTo(-1.38, 1.0);
    silhouette.bezierCurveTo(-1.17, 1.04, -1.01, 1.27, -0.82, 1.48);
    silhouette.bezierCurveTo(-0.68, 1.64, -0.49, 1.69, -0.22, 1.7);
    silhouette.bezierCurveTo(0.31, 1.72, 0.62, 1.57, 0.82, 1.37);
    silhouette.bezierCurveTo(1.02, 1.18, 1.08, 1.04, 1.36, 1.0);
    silhouette.lineTo(1.91, 0.92);
    silhouette.quadraticCurveTo(2.09, 0.89, 2.17, 0.73);
    silhouette.lineTo(2.21, 0.62);
    silhouette.quadraticCurveTo(2.22, 0.49, 2.1, 0.48);
    silhouette.closePath();
    const bodyGeometry = new THREE.ExtrudeGeometry(silhouette, {
      depth: 1.72,
      bevelEnabled: true,
      bevelSegments: 3,
      steps: 1,
      bevelSize: 0.045,
      bevelThickness: 0.035,
      curveSegments: 16,
    });
    bodyGeometry.translate(0, 0, -0.86);
    const body = new THREE.Mesh(bodyGeometry, paint);
    this.bodyGroup.add(body);

    const skirt = new THREE.Mesh(new RoundedBoxGeometry(3.55, 0.09, 1.78, 4, 0.04), darkTrim);
    skirt.position.y = 0.51;
    this.bodyGroup.add(skirt);

    const glassMaterial = glass.clone();
    glassMaterial.side = THREE.DoubleSide;
    const addSideGlass = (points: Array<[number, number]>, side: number) => {
      const shape = new THREE.Shape();
      shape.moveTo(points[0][0], points[0][1]);
      for (const [x, y] of points.slice(1)) shape.lineTo(x, y);
      shape.closePath();
      const geometry = new THREE.ExtrudeGeometry(shape, { depth: 0.018, bevelEnabled: false });
      const pane = new THREE.Mesh(geometry, glassMaterial);
      pane.position.z = side > 0 ? 0.867 : -0.885;
      this.bodyGroup.add(pane);
    };
    for (const side of [-1, 1]) {
      addSideGlass([[-1.45, 1.04], [-1.05, 1.41], [-0.88, 1.54], [-0.66, 1.59], [-0.25, 1.6], [-0.25, 1.06]], side);
      addSideGlass([[-0.16, 1.06], [-0.16, 1.6], [0.11, 1.58], [0.48, 1.45], [0.82, 1.13], [0.91, 1.04]], side);
    }

    const roofGlass = new THREE.Mesh(
      new RoundedBoxGeometry(1.18, 0.025, 1.38, 4, 0.015),
      glassMaterial,
    );
    roofGlass.position.set(-0.22, 1.695, 0);
    this.bodyGroup.add(roofGlass);

    const mirrorGeometry = new RoundedBoxGeometry(0.18, 0.07, 0.12, 3, 0.03);
    for (const side of [-1, 1]) {
      const mirror = new THREE.Mesh(mirrorGeometry, paint);
      mirror.position.set(0.65, 1.11, side * 0.91);
      mirror.castShadow = true;
      this.bodyGroup.add(mirror);
    }

    const accentBar = new THREE.Mesh(new THREE.BoxGeometry(0.025, 0.04, 1.05), this.accentMaterial);
    accentBar.position.set(2.18, 0.69, 0);
    this.bodyGroup.add(accentBar);

    for (const side of [-1, 1]) {
      const sill = new THREE.Mesh(new THREE.BoxGeometry(2.55, 0.025, 0.018), darkTrim);
      sill.position.set(0.02, 0.64, side * 0.88);
      this.bodyGroup.add(sill);
      for (const x of [-0.58, 0.71]) {
        const seam = new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.4, 0.012), darkTrim);
        seam.position.set(x, 0.91, side * 0.884);
        this.bodyGroup.add(seam);
      }
      const handle = new THREE.Mesh(new RoundedBoxGeometry(0.22, 0.025, 0.018, 2, 0.01), darkTrim);
      handle.position.set(0.08, 1.01, side * 0.89);
      this.bodyGroup.add(handle);
    }

    const headlightGeometry = new THREE.BoxGeometry(0.035, 0.075, 0.32);
    for (const side of [-1, 1]) {
      const light = new THREE.Mesh(headlightGeometry, this.headlightMaterial);
      light.position.set(2.13, 0.76, side * 0.55);
      this.bodyGroup.add(light);
    }

    const tailBar = new THREE.Mesh(new THREE.BoxGeometry(0.035, 0.06, 1.2), this.tailMaterial);
    tailBar.position.set(-2.18, 0.75, 0);
    this.bodyGroup.add(tailBar);

    const beacon = new THREE.Mesh(
      new RoundedBoxGeometry(0.34, 0.035, 0.13, 2, 0.02),
      this.beaconMaterial,
    );
    beacon.position.set(-0.2, 1.72, 0);
    this.bodyGroup.add(beacon);


    const tireMaterial = new THREE.MeshStandardMaterial({
      color: COLORS.tire,
      roughness: 0.9,
      metalness: 0.05,
    });
    const hubMaterial = new THREE.MeshStandardMaterial({
      color: COLORS.rule,
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
    const speedFactor = Math.min(1.6, Math.abs(input.speedKmh) / 90);
    const scrollFactor = input.rest || input.reducedMotion ? 0 : Math.min(1.5, Math.abs(input.scrollVelocity));
    const spin = speedFactor * scrollFactor * input.dt * 7;
    for (const wheel of this.wheels) {
      wheel.rotation.z -= spin;
    }

    this.headlightMaterial.color.set(COLORS.benchDeep);
    this.bodyGroup.position.y = input.rest ? -0.012 : 0;
  }
}
