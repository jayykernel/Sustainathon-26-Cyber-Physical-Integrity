import type { BackendEvent } from "../api";
import { formatSimTime } from "./format";

type Tone = "plain" | "alert" | "decoy" | "muted";
interface LogEntry { time: number; text: string; tone: Tone }

function requireElement<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Missing required element #${id}`);
  return element as T;
}

/** Displays only events received from the backend session stream. */
export class AttackerTerminal {
  private readonly lines = requireElement<HTMLOListElement>("terminal-lines");
  private readonly status = requireElement("terminal-status");
  private readonly entries: LogEntry[] = [];
  private readonly seen = new Set<string>();

  update(event: BackendEvent): void {
    const key = `${event.t}:${event.kind}:${event.text}`;
    if (this.seen.has(key)) return;
    this.seen.add(key);
    const tone: Tone = event.severity.toLowerCase() === "critical" || event.severity.toLowerCase() === "high"
      ? "alert" : event.kind.toLowerCase().includes("probe") ? "decoy" : "plain";
    this.entries.push({ time: event.t, text: event.text, tone });
    while (this.entries.length > 14) this.entries.shift();
    this.status.dataset.state = tone === "alert" ? "attack" : "idle";
    this.status.textContent = "backend";
    this.render();
  }

  reset(): void {
    this.entries.length = 0;
    this.seen.clear();
    this.status.dataset.state = "idle";
    this.status.textContent = "waiting";
    this.render();
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
