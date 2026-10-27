import * as THREE from "three";
import type { TimelineSample } from "../sim/timeline";
import { COLORS } from "../tokens";

/**
 * The attacker's relay node: a graphite monolith tethered to the pack by a
 * command beam used to visualize an injected simulation attack.
 */
export class HackerNode {
  readonly group = new THREE.Group();

  private readonly node = new THREE.Group();
  private readonly screenMaterial: THREE.MeshStandardMaterial;
  private readonly beam: THREE.Mesh;
  private readonly beamMaterial: THREE.MeshBasicMaterial;
  private readonly commandPackets: THREE.Mesh[] = [];
  private readonly commandCurve: THREE.QuadraticBezierCurve3;

  constructor() {
    this.node.position.set(-3.05, 0.42, -1.6);
    this.group.add(this.node);

    const shell = new THREE.Mesh(
      new THREE.BoxGeometry(0.54, 1.05, 0.5),
      new THREE.MeshStandardMaterial({
        color: COLORS.graphite,
        roughness: 0.78,
        metalness: 0.04,
      }),
    );
    shell.position.y = 0.55;
    shell.castShadow = true;
    this.node.add(shell);

    this.screenMaterial = new THREE.MeshStandardMaterial({
      color: COLORS.benchDeep,
      roughness: 0.82,
    });
    const screen = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.42, 0.02), this.screenMaterial);
    screen.position.set(0, 0.67, 0.26);
    this.node.add(screen);

    const mast = new THREE.Mesh(
      new THREE.CylinderGeometry(0.012, 0.012, 0.55, 8),
      new THREE.MeshStandardMaterial({ color: COLORS.inkSoft, roughness: 0.5 }),
    );
    mast.position.y = 1.35;
    this.node.add(mast);

    const antenna = new THREE.Mesh(new THREE.SphereGeometry(0.05, 16, 12), new THREE.MeshStandardMaterial({ color: COLORS.inkSoft, roughness: 0.82 }));
    antenna.position.y = 1.65;
    this.node.add(antenna);

    const start = new THREE.Vector3(-2.82, 1.42, -1.48);
    const end = new THREE.Vector3(0.15, 0.5, 0.1);

    const direction = end.clone().sub(start);
    const length = direction.length();
    this.beamMaterial = new THREE.MeshBasicMaterial({
      color: COLORS.inkSoft,
      transparent: true,
      opacity: 0.52,
    });
    this.beam = new THREE.Mesh(new THREE.CylinderGeometry(0.009, 0.009, length, 6), this.beamMaterial);
    this.beam.position.copy(start).lerp(end, 0.5);
    this.beam.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());
    this.beam.visible = false;
    this.group.add(this.beam);

    const commandControl = start.clone().lerp(end, 0.5).add(new THREE.Vector3(0, 0.75, 0));
    this.commandCurve = new THREE.QuadraticBezierCurve3(start, commandControl, end);
    const commandGeometry = new THREE.SphereGeometry(0.032, 10, 8);
    const commandMaterial = new THREE.MeshBasicMaterial({ color: COLORS.ink });
    for (let index = 0; index < 6; index += 1) {
      const packet = new THREE.Mesh(commandGeometry, commandMaterial);
      packet.visible = false;
      this.commandPackets.push(packet);
      this.group.add(packet);
    }

  }

  update(sample: TimelineSample, elapsed: number, reducedMotion: boolean): void {
    const attacking = sample.attackActive ?? false;
    this.screenMaterial.color.set(attacking ? COLORS.sheet : COLORS.benchDeep);
    this.beam.visible = attacking;
    this.beamMaterial.opacity = sample.twinActive ? 0.32 : 0.52;

    const showCommand = attacking && !sample.twinActive;
    for (let index = 0; index < this.commandPackets.length; index += 1) {
      const packet = this.commandPackets[index];
      packet.visible = showCommand && !reducedMotion;
      if (packet.visible) {
        const phase = (elapsed * 0.55 + index / this.commandPackets.length) % 1;
        packet.position.copy(this.commandCurve.getPoint(phase));
      }
    }
  }
}
