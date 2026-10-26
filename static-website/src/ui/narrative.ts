import { STAGES } from "../stages";

/** Builds the stage rail and keeps it in step with the scroll position. */
export class StageNav {
  private readonly buttons: HTMLButtonElement[] = [];
  private lastStage = -1;

  constructor(
    private readonly list: HTMLOListElement,
    private readonly reducedMotion: () => boolean,
  ) {
    STAGES.forEach((stage, index) => {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "rail__button";
      button.dataset.stage = String(index);

      const number = document.createElement("span");
      number.className = "rail__num";
      number.textContent = String(index + 1).padStart(2, "0");

      const label = document.createElement("span");
      label.className = "rail__label";
      label.textContent = stage.label;

      button.append(number, label);
      button.addEventListener("click", () => this.scrollToStage(index));
      item.append(button);
      this.list.append(item);
      this.buttons.push(button);
    });
  }

  update(stageIndex: number): void {
    if (stageIndex === this.lastStage) return;
    this.lastStage = stageIndex;
    this.buttons.forEach((button, index) => {
      if (index === stageIndex) button.setAttribute("aria-current", "step");
      else button.removeAttribute("aria-current");
    });
  }

  scrollToStage(index: number): void {
    window.scrollTo({
      top: Math.max(0, index) * window.innerHeight,
      behavior: this.reducedMotion() ? "auto" : "smooth",
    });
  }
}
