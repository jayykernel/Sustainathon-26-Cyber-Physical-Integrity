import { describe, expect, it } from "vitest";
import { AttackClassifier, type ClassifierConfig } from "../src/sim/classifier";

const config: ClassifierConfig = {
  nisThreshold: 11,
  window: 20,
  suspectFraction: 0.35,
  suspectReleaseFraction: 0.2,
  confirmedFraction: 0.75,
  residualThreshold_C: 1,
  confirmedResidual_C: 1.8,
  latchConfirmed: false,
};

function feed(
  classifier: AttackClassifier,
  count: number,
  nis: number,
  tempResidual: number,
): string[] {
  const verdicts: string[] = [];
  for (let index = 0; index < count; index += 1) {
    verdicts.push(classifier.update({ nis, tempResidual }));
  }
  return verdicts;
}

describe("attack classifier", () => {
  it("stays safe on nominal evidence", () => {
    const classifier = new AttackClassifier(config);
    const verdicts = feed(classifier, 40, 1.5, 0.1);
    expect(verdicts.every((verdict) => verdict === "safe")).toBe(true);
  });

  it("raises suspicion on sustained NIS evidence", () => {
    const classifier = new AttackClassifier(config);
    const verdicts = feed(classifier, 20, 18, 0.5);
    expect(verdicts).toContain("suspect");
    expect(verdicts).not.toContain("confirmed");
  });

  it("confirms with sustained NIS and strong residual evidence", () => {
    const classifier = new AttackClassifier(config);
    const verdicts = feed(classifier, 20, 18, 2.4);
    expect(verdicts.slice(0, 19).every((verdict) => verdict !== "confirmed")).toBe(true);
    expect(verdicts[19]).toBe("confirmed");
  });

  it("holds a suspect verdict until evidence falls below the release threshold", () => {
    const classifier = new AttackClassifier({ ...config, window: 10 });
    feed(classifier, 4, 18, 0.5); // suspicion raised
    feed(classifier, 6, 1, 0.1); // window full: 4 of 10, still suspect
    expect(classifier.classification).toBe("suspect");
    feed(classifier, 1, 1, 0.1); // 3 of 10: below 0.35, above 0.2
    expect(classifier.classification).toBe("suspect");
    feed(classifier, 1, 1, 0.1); // 2 of 10: at the release threshold
    expect(classifier.classification).toBe("suspect");
    feed(classifier, 1, 1, 0.1); // 1 of 10: below the release threshold
    expect(classifier.classification).toBe("safe");
  });

  it("recovers to safe after the evidence window clears when not latched", () => {
    const classifier = new AttackClassifier(config);
    feed(classifier, 20, 18, 2.4);
    expect(classifier.classification).toBe("confirmed");
    feed(classifier, 20, 1, 0.1);
    expect(classifier.classification).toBe("safe");
  });

  it("latches a confirmed verdict when configured", () => {
    const classifier = new AttackClassifier({ ...config, latchConfirmed: true });
    feed(classifier, 20, 18, 2.4);
    expect(classifier.classification).toBe("confirmed");
    feed(classifier, 40, 1, 0.1);
    expect(classifier.classification).toBe("confirmed");
  });

  it("does not confirm on a single spike", () => {
    const classifier = new AttackClassifier(config);
    classifier.update({ nis: 50, tempResidual: 5 });
    feed(classifier, 19, 1, 0.1);
    expect(classifier.classification).not.toBe("confirmed");
  });
});
