import * as THREE from "three";
import { COLORS } from "../tokens";

export interface EnvironmentRig {
  group: THREE.Group;
  update(tone: THREE.Color, alarm: boolean, elapsed: number, reducedMotion: boolean): void;
}

/**
 * Light studio bench around the vehicle: a ruled floor, a measurement ring, and
 * a few tick posts. The scene deliberately stays in the project's light
 * instrument palette instead of a dark "cyber" stage.
 */
export function createEnvironment(): EnvironmentRig {
  const group = new THREE.Group();

  const floorMaterial = new THREE.MeshStandardMaterial({
    color: COLORS.benchDeep,
    roughness: 0.94,
    metalness: 0,
  });
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(90, 90), floorMaterial);
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  group.add(floor);

  const grid = new THREE.GridHelper(90, 90, COLORS.rule, COLORS.rule);
  const gridMaterial = grid.material as THREE.Material;
  gridMaterial.transparent = true;
  gridMaterial.opacity = 0.55;
  grid.position.y = 0.004;
  group.add(grid);

  const accentMaterial = new THREE.MeshBasicMaterial({
    color: COLORS.protected,
    transparent: true,
    opacity: 0.6,
  });
  const ring = new THREE.Mesh(new THREE.TorusGeometry(3.55, 0.012, 6, 160), accentMaterial);
  ring.rotation.x = -Math.PI / 2;
  ring.position.y = 0.02;
  group.add(ring);

  const outerMaterial = new THREE.MeshBasicMaterial({
    color: COLORS.rule,
    transparent: true,
    opacity: 0.7,
  });
  const outerRing = new THREE.Mesh(new THREE.TorusGeometry(4.25, 0.006, 6, 160), outerMaterial);
  outerRing.rotation.x = -Math.PI / 2;
  outerRing.position.y = 0.02;
  group.add(outerRing);

  const tickMaterial = new THREE.MeshStandardMaterial({
    color: COLORS.rule,
    roughness: 0.8,
  });
  const tickGeometry = new THREE.BoxGeometry(0.03, 0.26, 0.03);
  const tickCount = 16;
  for (let index = 0; index < tickCount; index += 1) {
    const angle = (index / tickCount) * Math.PI * 2;
    const tick = new THREE.Mesh(tickGeometry, tickMaterial);
    tick.position.set(Math.cos(angle) * 4.25, 0.13, Math.sin(angle) * 4.25);
    tick.castShadow = true;
    group.add(tick);
  }

  const sweepMaterial = new THREE.MeshBasicMaterial({
    color: COLORS.protected,
    transparent: true,
    opacity: 0.22,
    side: THREE.DoubleSide,
  });
  const sweep = new THREE.Mesh(new THREE.RingGeometry(3.5, 3.62, 96, 1, 0, Math.PI / 3), sweepMaterial);
  sweep.rotation.x = -Math.PI / 2;
  sweep.position.y = 0.025;
  group.add(sweep);

  return {
    group,
    update(tone, alarm, elapsed, reducedMotion) {
      accentMaterial.color.copy(tone);
      sweepMaterial.color.copy(tone);
      const pulse = reducedMotion ? 0.5 : 0.5 + 0.5 * Math.sin(elapsed * 1.4);
      accentMaterial.opacity = alarm ? 0.45 + pulse * 0.4 : 0.38 + pulse * 0.2;
      sweep.rotation.z = reducedMotion ? 0 : elapsed * 0.16;
    },
  };
}
