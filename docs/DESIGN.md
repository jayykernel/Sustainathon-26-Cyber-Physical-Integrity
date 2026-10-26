# DESIGN.md — PhysiGuard frontend

Audience: hackathon judges and engineers watching a 3-minute demo, often on a projector, sometimes reading alone later.
Primary job: make one idea legible in seconds. **The same attack hits two identical batteries. One is protected, one is not. Watch their temperatures diverge, and see why the guard knew.**

The interface should feel like a measurement instrument, not a marketing page or a generic SaaS dashboard.

## 1. Design plan

**Concept: strip-chart recorder.** Time scrolls left to right like a chart recorder. The memorable element (the one place to spend boldness) is the **paired thermal trace**: true temperature of the unprotected battery (hazard color) against the protected battery (instrument blue), with the reported temperature as a dashed line, the model prediction as a thin line with a tolerance band, the hazard limit as a ruled line, and the attack window shaded with a labelled onset marker. Everything else is quiet, flat, and ruled.

### Color (named tokens; light theme only)
| Token | Hex | Use |
|---|---|---|
| `bench` | `#ECEFF1` | page background |
| `sheet` | `#FBFCFC` | working surfaces (charts, tables) |
| `rule` | `#C9D1D6` | 1 px borders and dividers (structure carries information) |
| `ink` | `#14232C` | primary text |
| `ink-soft` | `#52636D` | secondary text, axis labels |
| `protected` | `#1D5FA8` | protected plant, twin, SAFE_MODE |
| `hazard` | `#C23A22` | unprotected plant, hazard limit, CONFIRMED |
| `caution` | `#A86A12` | SUSPECT |
| `nominal` | `#1E7F5C` | NORMAL, clean evidence |

Contrast: all text meets WCAG AA on its surface. Color is never the only signal: states carry an icon and a word.

### Type
- **IBM Plex Sans** for everything (400, 500, 600), tabular figures on for all numbers (`font-variant-numeric: tabular-nums`). Plex's engineering character fits instrumentation without needing monospace labels.
- **IBM Plex Mono** only for literal code, seeds, hashes, and commands.
- Scale (px): 12 axis/captions, 14 body and controls, 16 section headings, 20 view titles, 32 single key figures. Line length under 75 characters in prose. Sentence case everywhere. No all-caps eyebrows, no tracked-out labels.

### Layout
Fixed left rail (nav + run identity), thin top status bar, content area. Panels are separated by rules, not floating cards: no drop shadows, one radius (4 px) for controls only, panels are square-edged.

```
+------+----------------------------------------------------------------------+
| rail | status: Live | seed 4242 | t 00:21:14 | 20× | connection ●            |
|      +----------------------------------------------------------------------+
| Con- | Attack: model synthesis (injected 00:15:02)        State: CONFIRMED  |
| sole | Margin to hazard: 11.4 °C   Detected 38 s after onset   Suspect: all |
| Lab  +------------------------------------------------------+---------------+
| Bench| TRUE TEMPERATURE                                     | What happened |
| Meth | unprotected ─── protected ─── reported - - predicted  |  timeline     |
|      | [ paired thermal trace, ~45% of height ]             |  00:15:02 ... |
|      +------------------------------------------------------+  00:15:40 ... |
|      | Evidence: NIS | CUSUM | Probe gain (three aligned    |  channel trust|
|      | strips sharing the time axis)                        |  V  I  T      |
|      +------------------------------------------------------+---------------+
|      | Current: request / command / safe limit   | controls: ▶ speed reset  |
|      | Attack dock: [type ▾] [Inject]  Operator reset                       |
+------+----------------------------------------------------------------------+
```
(Wireframe is structural. Use real components; the right column is 320 px.)

Alignment: left-aligned text, numbers right-aligned in tables, chart titles left. Nothing centered except empty states.

### Principles
1. **Cause and effect on one time axis.** Attack onset, first evidence, state changes, and response are marked on every chart with the same vertical guides.
2. **Show the counterfactual.** The unprotected plant is always visible in the console. It is the argument.
3. **Honest by layout.** Failures, limits, and the oracle attacker case get the same visual weight as successes in Benchmarks.
4. **Quiet chrome, loud data.** One bold element (the thermal trace). Controls and navigation are plain.
5. **Readable on a projector.** Presentation-scale toggle raises base size to 18 px and thickens lines.

## 2. Views

### Console (default)
Components: run header (attack, onset, state, margin to hazard, detection delay, suspect channel), paired thermal trace, evidence strips, current strip, event timeline, channel trust chips (V, I, T: trusted / suspect / replaced by virtual sensor), run controls (play, pause, speed 1/5/20/60×, reset with seed), attack dock (choose attack, Inject), operator reset button (only enabled in SAFE_MODE).
Empty state: "Start a run to see the guard work. Pick a scenario in Lab or press Play." with a Play button.
Latency: first frame within 1 s of Play; if not, show a connection message, not a spinner forever.

### Lab
Scenario list (from `/api/scenarios`) with plain descriptions, attacker knowledge level, and expected outcome *as stated by the evidence*, not hand-written promises. **Guided story** ("Attacker ladder"): steps run automatically, each with a caption beside the console:
1. Random spike: every detector catches it.
2. Slow drift: simple monitoring misses it; accumulated evidence catches it.
3. Model-synthesis attack: passive monitoring sees nothing wrong while the real battery heats.
4. Same attack, with a random probe: the forged telemetry does not respond; the guard catches it and limits the temperature.
5. Limit case: an attacker who knows the probe in real time defeats the check. We show this too.
Captions reference the live run values (for example, the margin at detection), never fixed numbers.

### Benchmarks
Data from `/api/benchmarks`. Detector ladder (range check, EKF, EKF + CUSUM, full PhysiGuard) as a table with detection rate and 95% CI, delay, margin at detection, hazard-event rate; grouped bars beside it; detection versus probe amplitude curve; delay distributions; localization confusion matrix with the scoring rule stated; probe overhead; false alarms per hour with CI; metadata block (git hash, config hash, seeds, date) and the command that reproduces it. Failure rows are not hidden or collapsed.
Missing results: "No benchmark results found. Run `make eval`, then reload." with the command in a copy field.

### Method
Architecture SVG (plant, telemetry path, attacker, guard, probe, response), the equations from SPEC (rendered, not images of text), threat-model table (A0/A1/A2), limits and out-of-scope list from `/api/limits`.

## 3. Components and states
Every data-driven component implements loading, empty, error, and offline-replay states. Replay banner (always visible while replaying): "Replaying a recorded run. This is not live." Connection indicator: connected, reconnecting (with attempt count), offline. Errors say what failed and what to do, for example "Lost connection to the simulator. Reconnecting (attempt 2). You can also replay a recorded run." No apologies, no vague messages.

Charts (ECharts): no animation on streaming series; 1.5 px lines (2.5 px in presentation mode); direct labels at line ends in addition to legend; dashed for reported, thin for predicted, band for ±2σ prediction tolerance; limits as labelled rules; attack window as a tinted band with an onset marker; shared time axis and synchronized crosshair across the strips; max 900 points per series (rolling window, decimated); tooltips show values with units.

Motion: none for streaming data. Opening panels and state changes may use 150 ms opacity or position transitions. Respect `prefers-reduced-motion`. No entrance animations on page load.

## 4. Copy rules
- Sentence case; plain verbs; one job per label. Buttons name the action: "Inject attack", "Reset run", "Reset to normal".
- State names in the UI: Normal, Suspect, Confirmed, Safe mode.
- Say "simulated" wherever a physical outcome is shown. Never "safe", "secure", or "prevented"; say "limited", "detected", "kept below the simulated limit".
- Numbers always carry units. Times as mm:ss since run start.
- No emoji, no "→" appended to links, no middle-dot meta strings, no slogans, no lorem ipsum, no placeholder data.

## 5. Quality floor (checked in P9f and P10)
- Keyboard: every control reachable, visible focus ring (2 px `protected` outline), logical order, Esc closes dialogs.
- Screen reader: state changes announced via `aria-live="polite"`, charts have text summaries (latest values and state), tables are real tables.
- Responsive: designed for 1280×720 and up; usable at 768 (right column collapses under charts).
- Performance: stays at 60 fps UI at 60× simulation speed with all strips rendering; verify.
- Offline: fonts, icons, and charts bundled; no external requests (verify in the network panel).

## 6. Things that read as "vibe-coded" — do not do
Gradient or glass panels, identical rounded cards in a grid, colored glow on status, emoji icons, fake live numbers, charts with default ECharts/Recharts palettes, dark theme with a neon accent, centered hero text, loading spinners with no message, "AI-powered" badges, unexplained acronyms on screen (define NIS, CUSUM, EKF on first use with a tooltip).
