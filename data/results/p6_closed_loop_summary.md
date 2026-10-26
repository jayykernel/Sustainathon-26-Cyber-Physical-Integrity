# P6 paired closed-loop validation

Validation seeds: 0–9; duration: 3600 s per run.

| Attack | Peak T undefended / defended (°C) | Peak V undefended / defended (V) | Hazard rate undefended / defended | Paired Δ peak T / Δ peak V |
|---|---:|---:|---:|---:|
| AT2 | 52.13 / 43.76 | 4.1879 / 3.8334 | 0% / 0% | 8.37 °C / 0.3545 V |
| AT3 | 52.18 / 43.78 | 4.2858 / 3.8313 | 30% / 0% | 8.40 °C / 0.4545 V |
| AT4 | 47.24 / 43.78 | 4.0527 / 3.8325 | 0% / 0% | 3.46 °C / 0.2202 V |
| AT5 | 47.96 / 43.76 | 4.3160 / 3.8334 | 100% / 0% | 4.20 °C / 0.4826 V |

A positive paired delta means the defended run had a lower peak. Failures remain visible in the per-seed JSON and are not removed from the summary.
