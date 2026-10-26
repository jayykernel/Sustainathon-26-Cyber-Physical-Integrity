# PhysiGuard — battery integrity bench

A scrollable 3D simulation of an electric vehicle battery hijack: a forged thermal
channel, an extended Kalman filter that catches the lie, a one-RC digital twin that
answers the attacker with fabricated data, and a vehicle that comes to rest.

Everything runs in the browser from a fixed seed. There is no backend, no network
request at runtime, and no real telemetry.

## Run it

Requires Node.js 18 or newer.

```bash
npm install
npm run dev      # http://localhost:4173
```

Other scripts:

```bash
npm test         # 28 unit tests for the models and the full timeline
npm run typecheck
npm run build    # type-check, then emit a static site in dist/
npm run preview  # serve the production build at http://localhost:4173
```

`dist/` uses relative asset paths, so it can be served by any static host or opened
through a local static server. Use `npm run preview` rather than `file://`, because
browsers block module scripts loaded from the filesystem.

## What the page shows

| # | Stage | Simulated time | What happens |
|---|---|---|---|
| 1 | Normal drive | 0:00 – 2:00 | Stable pack; reported, modelled, and true temperature agree. |
| 2 | Hijack | 2:00 – 4:00 | Thermal channel is spoofed; reported temperature drifts away from physics. |
| 3 | Alarms | 4:00 – 6:00 | Classifier is suspicious, the cabin turns red, traction derates. |
| 4 | Detection | 6:00 – 8:00 | EKF stage; attack is confirmed at 6:10 (370 s), twin is seeded. |
| 5 | Digital twin | 8:00 – 10:00 | Wireframe twin is engaged and listening on the forged channel. |
| 6 | Deception | 10:00 – 11:00 | Twelve fabricated packets; the twin falls silent at 10:55. |
| 7 | Rest mode | 11:00 – 12:00 | Speed reaches zero, alarms clear, the twin stays silent. |

Scroll position maps linearly onto the twelve-minute timeline: seven full-viewport
stages plus a footer, one stage per two minutes (one minute for the last two).
The stage rail jumps to any stage.

### Reading the interface

- **Top bar** — simulated clock, speed, classifier chip, telemetry channel, mode.
- **Stage rail** — the seven narrative stages; the current one is highlighted.
- **Narrative card** — one short brief per stage, with the stage accent colour.
- **HUD** — true / reported / 1RC-model temperatures, residual, NIS, state of charge,
  rolling evidence, the strip-chart recorder, twin state, and the attacker log.
- **Scene** — primitive-built electric car, floor pack with ten cells, attacker relay,
  and the twin ghost. Each stage has its own camera framing; stage 4 goes underbody.
- **Attacker channel** — a timestamped log whose entries are generated from the same
  deterministic timeline as everything else.

The chart always draws the full 0–12 minute axis and reveals the trace as you scroll.
The classifier ribbon above the plot shows exactly when the verdict was safe, suspect,
or confirmed, and the shaded band marks the attack window.

## How the simulation works

The whole run is computed once, at load time, by `buildTimeline()` in
`src/sim/timeline.ts`. Each simulated second produces one `TimelineSample`; scroll
position selects a sample. Because the timeline is precomputed, the scene, chart, HUD,
terminal, and classifier can never disagree, no matter how fast the page is scrolled.

### One-RC battery model

`src/sim/twin.ts` implements a first-order RC equivalent circuit:

- coulomb-counted state of charge,
- one RC branch for polarization voltage (`R1`, `tau1`),
- a lumped thermal node driven by `I²R` losses and ambient cooling,
- an open-circuit-voltage table indexed by state of charge.

An internal "plant" instance plays the real pack. A second, independent instance
(`shadowTwin`) predicts what the pack *should* be doing; its temperature is the
reference for the 1RC model readout.

### EKF detection

`src/sim/ekf.ts` estimates state of charge, polarization voltage, and cell temperature
from the reported voltage and temperature. The normalized innovation squared (NIS)
gates the measurement, and the temperature innovation is compared against the
independent physical prediction.

`src/sim/classifier.ts` turns the innovation stream into a verdict. A single spike is
never enough:

- rolling window of 20 samples,
- NIS gate of 11 (roughly the 99.5 % chi-square bound for two degrees of freedom),
- **suspect** when at least 35 % of the window is outside tolerance,
- **confirmed** when at least 75 % of the window carries a strong (> 2.2 °C)
  temperature residual against the physical model,
- confirmation latches for the rest of the run,
- a 20 % release threshold keeps a brief clean sample from flipping the HUD back to
  safe in the middle of the attack.

In the shipped scenario the verdict becomes suspect at 3:38 (218 s) and confirmed at
6:10 (370 s).

### Digital twin and deception

On confirmation, a third one-RC instance is seeded from the EKF's state of charge and
the physical model's fast states. `src/sim/fakeData.ts` generates twelve fabricated
temperature/SOC packets between 10:00 and 10:55, then stops responding. The attacker
log records each packet and the lost uplink.

The physical pack peaks around 50.4 °C — below the 55 °C hazard line — while the
spoofed channel reports above 52 °C. The point is that the reported number, not the
pack, becomes the emergency.

### Rest mode

At 11:00 the uplink closes, alarms clear, wheels stop, and the car settles. Speed
reaches zero a few seconds later. The classifier stays confirmed, because the attack
did happen; the vehicle is simply no longer responding to it.

## Project layout

```
static-website/
├── index.html              page structure and all narrative copy
├── src/
│   ├── main.ts             scroll mapping, RAF loop, boot and error handling
│   ├── config.ts           battery, sensor, detection, and scenario parameters
│   ├── stages.ts           stage order and scroll → simulated-time mapping
│   ├── tokens.ts           shared colour tokens
│   ├── style.css           layout, HUD, rail, chart legend, responsive rules
│   ├── sim/
│   │   ├── twin.ts         one-RC battery model
│   │   ├── ekf.ts          extended Kalman filter
│   │   ├── classifier.ts   safe / suspect / confirmed state machine
│   │   ├── fakeData.ts     fabricated packet generator and silence behaviour
│   │   ├── linalg.ts       small matrix helpers used by the EKF
│   │   └── timeline.ts     deterministic 720 s scenario
│   ├── scene/
│   │   ├── world.ts        renderer, lights, camera keyframes
│   │   ├── car.ts          primitives-based EV and state lighting
│   │   ├── battery.ts      floor pack, cells, sensor pod, twin ghost
│   │   ├── hacker.ts       attacker relay, beam, packet arcs
│   │   └── environment.ts  bench floor, measurement rings, sweep
│   └── ui/
│       ├── hud.ts          telemetry and classifier readouts
│       ├── chart.ts        strip-chart canvas recorder
│       ├── hacker.ts       attacker channel log
│       ├── narrative.ts    stage rail
│       └── format.ts       time and label formatting
└── tests/                  model and timeline tests (Vitest)
```

## Using the models directly

The models have no DOM or Three.js dependency, so they can be reused or inspected
from a test or a Node script:

```ts
import { buildTimeline } from "./src/sim/timeline";

const timeline = buildTimeline();      // deterministic 720 s run
const sample = timeline.sampleAt(370); // 6:10, the confirmation moment

console.log(sample.classification);    // "confirmed"
console.log(sample.trueTempC);         // physical pack temperature
console.log(sample.reportedTempC);     // spoofed channel
console.log(sample.twinActive);        // true from this sample onwards
```

`OneRcTwin`, `Ekf`, `AttackClassifier`, and `FakeDataInjector` each expose a small
step/update API and are exercised directly in `tests/`.

## Verification

```bash
npm test         # 28 tests: twin, EKF, classifier, fake data, full timeline
npm run typecheck
npm run build
```

The timeline tests assert the narrative order end to end: safe at the start,
suspicion before confirmation, confirmation during the EKF stage, no un-confirming,
twin engagement only after confirmation, twelve packets followed by silence, alarms
cleared at rest, monotonic stage progression, and the true pack staying below the
hazard limit.

## Accessibility and compatibility

- Skip link, stage buttons, `aria-live` stage/verdict announcements, and a descriptive
  `aria-label` on the temperature chart.
- `prefers-reduced-motion` disables camera easing, alarms pulsing, packet motion, and
  smooth scrolling.
- The layout collapses the rail and turns the HUD into a bottom strip below 960 px;
  below 720 px the chart is hidden and the status panel remains.
- WebGL is required for the 3D scene. If a context cannot be created, the boot overlay
  shows an explanatory error instead of a blank canvas.
- Fonts (IBM Plex Sans/Mono) are bundled; the page makes no external requests.

## Scope and limitations

This is a teaching model, not a vehicle interface or a battery management system.

- Ten cells are visual only; the simulation integrates one lumped thermal node.
- The 1RC and EKF parameters mirror the backend defaults in `configs/default.yaml`,
  but they are not identified or validated against a real pack.
- The attack is a scripted thermal-sensor spoof plus a manipulated current request.
  It does not model CAN arbitration, message authentication, or a real intrusion path.
- There is no hardware, no live bus, and no real telemetry. Every number is generated.
- The twin's fabricated data is illustrative; it is not a defensive countermeasure
  that should be deployed.

The visual language follows [`docs/DESIGN.md`](../docs/DESIGN.md): a light measurement
bench, ruled panels, IBM Plex, and the hazard / caution / protected / nominal accents.
The change that introduced this site is documented in
[`openspec/changes/electric-car-hack-simulation`](../openspec/changes/electric-car-hack-simulation).
