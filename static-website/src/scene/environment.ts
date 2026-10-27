import * as THREE from "three";
import { COLORS, colorForClassification } from "../tokens";
import type { Classification } from "../sim/classifier";

export interface EnvironmentRig {
  group: THREE.Group;
  setState(classification: Classification): void;
}

/** Neutral studio floor with fine technical grid and a non-state ground ring. */
export function createEnvironment(): EnvironmentRig {
  const group = new THREE.Group();
  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(90, 90),
    new THREE.MeshStandardMaterial({ color: COLORS.benchDeep, roughness: 0.86, metalness: 0.02 }),
  );
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  group.add(floor);

  const grid = new THREE.GridHelper(90, 90, COLORS.rule, COLORS.rule);
  const gridMaterial = grid.material as THREE.Material;
  gridMaterial.transparent = true;
  gridMaterial.opacity = 0.16;
  grid.position.y = 0.004;
  group.add(grid);

  const circlePoints: THREE.Vector3[] = [];
  for (let index = 0; index < 192; index += 1) {
    const angle = (index / 192) * Math.PI * 2;
    circlePoints.push(new THREE.Vector3(Math.cos(angle) * 3.55, 0.02, Math.sin(angle) * 3.55));
  }
  const ringGeometry = new THREE.BufferGeometry().setFromPoints(circlePoints);
  const ringMaterial = new THREE.LineBasicMaterial({ color: COLORS.nominal, transparent: true, opacity: 0.42 });
  group.add(new THREE.LineLoop(ringGeometry, ringMaterial));

  const tickMaterial = new THREE.MeshStandardMaterial({ color: COLORS.rule, roughness: 0.86, metalness: 0.02 });
  const tickGeometry = new THREE.BoxGeometry(0.025, 0.16, 0.025);
  for (let index = 0; index < 16; index += 1) {
    const angle = (index / 16) * Math.PI * 2;
    const tick = new THREE.Mesh(tickGeometry, tickMaterial);
    tick.position.set(Math.cos(angle) * 4.25, 0.08, Math.sin(angle) * 4.25);
    group.add(tick);
  }

  return {
    group,
    setState(classification) {
      ringMaterial.color.set(colorForClassification(classification));
    },
  };
}
