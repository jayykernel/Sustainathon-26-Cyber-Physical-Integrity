import type { BackendEvent } from "../api";
import { formatSimTime } from "./format";

type Tone = "plain" | "alert" | "probe" | "muted";
interface LogEntry { time: number; text: string; tone: Tone; severity: string }

function requireElement<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Missing required element #${id}`);
  return element as T;
}

/** Displays only events received from the backend session stream. */
export class AttackerTerminal {
  private readonly lines = requireElement<HTMLOListElement>("terminal-lines");
  private readonly status = requireElement("terminal-status");
  private readonly toast = requireElement<HTMLElement>("event-toast");
  private readonly entries: LogEntry[] = [];
  private readonly seen = new Set<string>();
  private toastTimer: number | null = null;

  notify(message: string): void {
    this.toast.textContent = message;
    this.toast.hidden = false;
    if (this.toastTimer !== null) window.clearTimeout(this.toastTimer);
    this.toastTimer = window.setTimeout(() => {
      this.toast.hidden = true;
      this.toastTimer = null;
    }, 4200);
  }

  update(event: BackendEvent): void {
    const key = `${event.t}:${event.kind}:${event.text}`;
    if (this.seen.has(key)) return;
    this.seen.add(key);
    const tone: Tone = event.severity.toLowerCase() === "critical" || event.severity.toLowerCase() === "high"
      ? "alert" : event.kind.toLowerCase().includes("probe") ? "probe" : "plain";
    this.entries.push({ time: event.t, text: event.text, tone, severity: event.severity.toLowerCase() });
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
    this.toast.hidden = true;
    if (this.toastTimer !== null) window.clearTimeout(this.toastTimer);
    this.toastTimer = null;
    this.render();
  }

  private render(): void {
    this.lines.replaceChildren();
    if (this.entries.length === 0) {
      const empty = document.createElement("li");
      empty.className = "terminal__empty";
      empty.textContent = "No events yet · awaiting backend stream";
      this.lines.append(empty);
      return;
    }
    for (const entry of this.entries) {
      const item = document.createElement("li");
      item.className = `terminal__line terminal__line--${entry.tone}`;
      const time = document.createElement("span");
      time.className = "terminal__time";
      time.textContent = formatSimTime(entry.time);
      const tag = document.createElement("span");
      tag.className = `terminal__tag terminal__tag--${entry.tone}`;
      tag.textContent = entry.tone === "alert" ? "ALERT" : ["medium", "moderate", "warning", "warn"].includes(entry.severity) ? "WARN" : "INFO";
      const text = document.createElement("span");
      text.className = "terminal__text";
      text.textContent = entry.text;
      item.append(time, tag, text);
      this.lines.append(item);
    }
    this.lines.scrollTop = this.lines.scrollHeight;
  }
}
