import * as THREE from "three";
import { SIMULATION } from "../config";
import type { TimelineSample } from "../sim/timeline";
import { COLORS } from "../tokens";

/**
 * The attacker's relay node: a graphite monolith tethered to the pack by a
 * thin command beam. Fabricated twin packets travel back along a raised arc.
 */
export class HackerNode {
  readonly group = new THREE.Group();

  private readonly node = new THREE.Group();
  private readonly screenMaterial: THREE.MeshStandardMaterial;
  private readonly antennaMaterial: THREE.MeshStandardMaterial;
  private readonly ringA: THREE.Mesh;
  private readonly ringB: THREE.Mesh;
  private readonly beam: THREE.Mesh;
  private readonly beamMaterial: THREE.MeshBasicMaterial;
  private readonly nodeLight: THREE.PointLight;
  private readonly commandPackets: THREE.Mesh[] = [];
  private readonly decoyPackets: THREE.Mesh[] = [];
  private readonly commandCurve: THREE.QuadraticBezierCurve3;
  private readonly decoyCurve: THREE.QuadraticBezierCurve3;

  constructor() {
    this.node.position.set(-3.05, 0.42, -1.6);
    this.group.add(this.node);

    const shell = new THREE.Mesh(
      new THREE.BoxGeometry(0.54, 1.05, 0.5),
      new THREE.MeshStandardMaterial({
        color: COLORS.graphite,
        roughness: 0.42,
        metalness: 0.6,
      }),
    );
    shell.position.y = 0.55;
    shell.castShadow = true;
    this.node.add(shell);

    this.screenMaterial = new THREE.MeshStandardMaterial({
      color: COLORS.ink,
      emissive: COLORS.hazard,
      emissiveIntensity: 0.15,
      roughness: 0.3,
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

    this.antennaMaterial = new THREE.MeshStandardMaterial({
      color: COLORS.caution,
      emissive: COLORS.caution,
      emissiveIntensity: 0.2,
      roughness: 0.35,
    });
    const antenna = new THREE.Mesh(new THREE.SphereGeometry(0.05, 16, 12), this.antennaMaterial);
    antenna.position.y = 1.65;
    this.node.add(antenna);

    const ringMaterial = new THREE.MeshBasicMaterial({
      color: COLORS.caution,
      transparent: true,
      opacity: 0.5,
    });
    this.ringA = new THREE.Mesh(new THREE.TorusGeometry(0.55, 0.007, 4, 72), ringMaterial);
    this.ringA.rotation.x = -Math.PI / 2;
    this.ringA.position.y = 0.32;
    this.node.add(this.ringA);

    this.ringB = new THREE.Mesh(
      new THREE.TorusGeometry(0.42, 0.006, 4, 64),
      new THREE.MeshBasicMaterial({ color: COLORS.hazard, transparent: true, opacity: 0.35 }),
    );
    this.ringB.position.y = 0.68;
    this.ringB.rotation.y = Math.PI / 2;
    this.node.add(this.ringB);

    this.nodeLight = new THREE.PointLight(COLORS.hazard, 0, 5, 2);
    this.nodeLight.position.set(0, 0.9, 0.4);
    this.node.add(this.nodeLight);

    const start = new THREE.Vector3(-2.82, 1.42, -1.48);
    const end = new THREE.Vector3(0.15, 0.5, 0.1);

    const direction = end.clone().sub(start);
    const length = direction.length();
    this.beamMaterial = new THREE.MeshBasicMaterial({
      color: COLORS.hazard,
      transparent: true,
      opacity: 0.4,
    });
    this.beam = new THREE.Mesh(new THREE.CylinderGeometry(0.009, 0.009, length, 6), this.beamMaterial);
    this.beam.position.copy(start).lerp(end, 0.5);
    this.beam.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());
    this.beam.visible = false;
    this.group.add(this.beam);

    const commandControl = start.clone().lerp(end, 0.5).add(new THREE.Vector3(0, 0.75, 0));
    this.commandCurve = new THREE.QuadraticBezierCurve3(start, commandControl, end);
    const decoyControl = end.clone().lerp(start, 0.5).add(new THREE.Vector3(0, 1.35, 0));
    this.decoyCurve = new THREE.QuadraticBezierCurve3(end, decoyControl, start);

    const commandGeometry = new THREE.SphereGeometry(0.032, 10, 8);
    const commandMaterial = new THREE.MeshBasicMaterial({ color: COLORS.hazard });
    for (let index = 0; index < 6; index += 1) {
      const packet = new THREE.Mesh(commandGeometry, commandMaterial);
      packet.visible = false;
      this.commandPackets.push(packet);
      this.group.add(packet);
    }

    const decoyGeometry = new THREE.SphereGeometry(0.04, 10, 8);
    const decoyMaterial = new THREE.MeshBasicMaterial({ color: COLORS.protected });
    for (let index = 0; index < 10; index += 1) {
      const packet = new THREE.Mesh(decoyGeometry, decoyMaterial);
      packet.visible = false;
      this.decoyPackets.push(packet);
      this.group.add(packet);
    }
  }

  update(sample: TimelineSample, elapsed: number, reducedMotion: boolean): void {
    const attacking = sample.t >= 120 && sample.t < SIMULATION.restAt_s;
    const decoying = sample.twinResponding && sample.fakePackets > 0;
    const pulse = reducedMotion ? 1 : 0.5 + 0.5 * Math.sin(elapsed * 4.4);

    this.screenMaterial.emissiveIntensity = attacking ? 0.55 + pulse * 1.5 : 0.12;
    this.antennaMaterial.emissiveIntensity = attacking ? 0.5 + pulse * 1.6 : 0.14;
    this.nodeLight.intensity = attacking ? 0.5 + pulse * 0.9 : 0;
    this.beam.visible = attacking;
    this.beamMaterial.opacity = sample.twinActive ? 0.2 : 0.28 + pulse * 0.3;

    if (!reducedMotion) {
      this.ringA.rotation.z = elapsed * 0.7;
      this.ringB.rotation.x = Math.PI / 2 + elapsed * 0.55;
      this.node.position.y = 0.42 + (attacking ? Math.sin(elapsed * 1.8) * 0.03 : 0);
    }

    const showCommand = attacking && !sample.twinActive;
    for (let index = 0; index < this.commandPackets.length; index += 1) {
      const packet = this.commandPackets[index];
      packet.visible = showCommand && !reducedMotion;
      if (packet.visible) {
        const phase = (elapsed * 0.55 + index / this.commandPackets.length) % 1;
        packet.position.copy(this.commandCurve.getPoint(phase));
      }
    }

    for (let index = 0; index < this.decoyPackets.length; index += 1) {
      const packet = this.decoyPackets[index];
      packet.visible = decoying && !reducedMotion;
      if (packet.visible) {
        const phase = (elapsed * 0.34 + index / this.decoyPackets.length) % 1;
        packet.position.copy(this.decoyCurve.getPoint(phase));
      }
    }
  }
}
