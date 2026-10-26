import { DETECTION } from "../config";

export type Classification = "safe" | "suspect" | "confirmed";

export interface ClassifierInput {
  /** Normalised innovation squared from the EKF. */
  nis: number;
  /** Temperature innovation in degrees Celsius (reported minus predicted). */
  tempResidual: number;
}

export interface ClassifierEvidence {
  windowSize: number;
  nisFraction: number;
  residualFraction: number;
  strongResidualFraction: number;
}

export interface ClassifierConfig {
  nisThreshold: number;
  window: number;
  suspectFraction: number;
  suspectReleaseFraction: number;
  confirmedFraction: number;
  residualThreshold_C: number;
  confirmedResidual_C: number;
  latchConfirmed: boolean;
}

/**
 * Classify a stream of EKF innovations as safe, suspect, or confirmed attack.
 *
 * A single spike is not enough. The classifier requires a fraction of a rolling
 * window to carry evidence, and confirmation additionally requires strong
 * temperature innovations. This mirrors the conservative state machine in the
 * backend response layer.
 */
export class AttackClassifier {
  private readonly config: ClassifierConfig;
  private history: ClassifierInput[] = [];
  private current: Classification = "safe";

  constructor(config: ClassifierConfig = DETECTION) {
    this.config = config;
  }

  get classification(): Classification {
    return this.current;
  }

  get evidence(): ClassifierEvidence {
    const windowSize = this.history.length;
    if (windowSize === 0) {
      return { windowSize: 0, nisFraction: 0, residualFraction: 0, strongResidualFraction: 0 };
    }
    let nisHits = 0;
    let residualHits = 0;
    let strongResidualHits = 0;
    for (const sample of this.history) {
      if (sample.nis > this.config.nisThreshold) nisHits += 1;
      const magnitude = Math.abs(sample.tempResidual);
      if (magnitude > this.config.residualThreshold_C) residualHits += 1;
      if (magnitude > this.config.confirmedResidual_C) strongResidualHits += 1;
    }
    return {
      windowSize,
      nisFraction: nisHits / windowSize,
      residualFraction: residualHits / windowSize,
      strongResidualFraction: strongResidualHits / windowSize,
    };
  }

  update(input: ClassifierInput): Classification {
    this.history.push({ nis: input.nis, tempResidual: input.tempResidual });
    while (this.history.length > this.config.window) this.history.shift();

    const evidence = this.evidence;
    const fullWindow = evidence.windowSize >= this.config.window;
    // A confirmation needs sustained strong residuals against the physical
    // model. An innovation statistic alone can be noisy, so NIS drives
    // suspicion while the model residual carries the confirmation.
    const confirmed =
      fullWindow && evidence.strongResidualFraction >= this.config.confirmedFraction;
    const aboveEnter =
      evidence.nisFraction >= this.config.suspectFraction ||
      evidence.residualFraction >= this.config.suspectFraction;
    // Hysteresis: once suspicious, hold the verdict until the evidence falls
    // below a lower release threshold. This prevents a single clean sample from
    // flipping the HUD back to "safe" in the middle of an attack.
    const aboveRelease =
      evidence.nisFraction >= this.config.suspectReleaseFraction ||
      evidence.residualFraction >= this.config.suspectReleaseFraction;
    const suspect = aboveEnter || (this.current !== "safe" && aboveRelease);

    let next: Classification = "safe";
    if (confirmed) next = "confirmed";
    else if (suspect) next = "suspect";

    if (this.config.latchConfirmed && this.current === "confirmed") next = "confirmed";
    this.current = next;
    return next;
  }

  reset(): void {
    this.history = [];
    this.current = "safe";
  }
}
