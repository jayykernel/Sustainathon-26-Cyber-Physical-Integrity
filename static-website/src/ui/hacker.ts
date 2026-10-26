import type { TimelineSample } from "../sim/timeline";
import { formatSimTime } from "./format";

type Tone = "plain" | "alert" | "decoy" | "muted";

interface LogEntry {
  time: number;
  text: string;
  tone: Tone;
}

interface Candidate {
  key: string;
  text: string;
  tone: Tone;
}

function requireElement<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Missing required element #${id}`);
  return element as T;
}

/**
 * The attacker's channel log. It narrates the same deterministic timeline the
 * scene and the classifier use, so the terminal never invents its own events.
 */
export class AttackerTerminal {
  private readonly lines = requireElement<HTMLOListElement>("terminal-lines");
  private readonly status = requireElement("terminal-status");
  private readonly emitted = new Set<string>();
  private readonly entries: LogEntry[] = [];
  private lastT = -1;

  update(sample: TimelineSample): void {
    if (sample.t === this.lastT) return;
    this.lastT = sample.t;

    const candidates: Candidate[] = [
      { key: "listener", text: "passive listener on CAN bus", tone: "muted" },
    ];

    if (sample.t >= 120) {
      candidates.push({ key: "spoof", text: "thermal channel 0x7E0 spoofed", tone: "alert" });
    }
    if (sample.t >= 240) {
      candidates.push({ key: "torque", text: "traction command accepted: 420 Nm", tone: "alert" });
    }
    if (sample.classification === "suspect") {
      candidates.push({ key: "suspect", text: "EKF verdict: suspect", tone: "alert" });
    }
    if (sample.classification === "confirmed") {
      candidates.push({ key: "confirmed", text: "EKF verdict: confirmed malware", tone: "alert" });
    }
    if (sample.twinActive) {
      candidates.push({ key: "handshake", text: "decoy handshake accepted", tone: "decoy" });
    }
    if (sample.lastFake && sample.fakePackets > 0) {
      candidates.push({
        key: `packet-${sample.fakePackets}`,
        text: `packet ${sample.fakePackets}: T=${sample.lastFake.tempC.toFixed(1)} °C SOC=${Math.round(
          sample.lastFake.soc * 100,
        )} %`,
        tone: "decoy",
      });
    }
    if (sample.twinActive && !sample.twinResponding) {
      candidates.push({ key: "closed", text: "decoy uplink lost", tone: "alert" });
      candidates.push({ key: "no-response", text: "no response from battery", tone: "muted" });
    }

    let changed = false;
    for (const candidate of candidates) {
      if (this.emitted.has(candidate.key)) continue;
      this.emitted.add(candidate.key);
      this.entries.push({ time: sample.t, text: candidate.text, tone: candidate.tone });
      changed = true;
    }

    while (this.entries.length > 14) this.entries.shift();
    if (changed) this.render();

    if (sample.t < 120) {
      this.setStatus("idle", "idle");
    } else if (sample.twinActive && !sample.twinResponding) {
      this.setStatus("silent", "silent");
    } else if (sample.twinResponding && sample.fakePackets > 0) {
      this.setStatus("decoy", "decoy");
    } else {
      this.setStatus("attack", "attack");
    }
  }

  private setStatus(state: string, label: string): void {
    this.status.dataset.state = state;
    this.status.textContent = label;
  }

  private render(): void {
    this.lines.replaceChildren();
    for (const entry of this.entries) {
      const item = document.createElement("li");
      item.className = `terminal__line terminal__line--${entry.tone}`;

      const time = document.createElement("span");
      time.className = "terminal__time";
      time.textContent = formatSimTime(entry.time);

      const text = document.createElement("span");
      text.className = "terminal__text";
      text.textContent = entry.text;

      item.append(time, text);
      this.lines.append(item);
    }
    this.lines.scrollTop = this.lines.scrollHeight;
  }
}
