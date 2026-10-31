# Verity — verification (partial, measured 31 Oct 2026, cloud Linux sandbox)

Everything below is a real run on live Gemini (10 rotating keys). Nothing is estimated. Sample size is tiny (one run per scenario, synthetic evidence) — treat as a smoke test, not a benchmark.

## Commands and results
| Command | Result |
|---|---|
| `cd backend && .venv/bin/python -m pytest -q` | 78 passed |
| `python scripts/e2e_check.py` (live) | 19/20 passed; the one failure ("data-error hypothesis present") was a real bug, fixed in `722b4a3`; e2e not re-run since |
| `python scripts/run_lab.py` (live, one scenario at a time) | see below (run still in progress when this was written) |

e2e values observed: quoted total 35700.00, recomputed 35700.00, proposed settlement 22300.00, 5/5 gates pass, report.pdf 11,013 bytes.

## Proof Lab (first 4 scenarios; later ones not yet recorded here)
| Scenario | Result | Latency | Note |
|---|---|---|---|
| consistent | PASS (9/9 assertions) | 39 s | |
| rear_vs_front | PASS | 15 s | |
| twist_secondary_impact | FAIL (1 assertion) | 82 s | Stale re-open worked (F-01, F-02, F-Z1 went stale on the new evidence) but the model added no new finding ids, so "At least 1 finding added" got 0. Real model behaviour, not an evaluator bug. The expectation in `fixtures/twist_secondary_impact/expected.json` (`delta.added_min: 1`) may be too strict — left unedited for the owner to decide. |
| bad_estimate | FAIL (1 assertion) | 13 s | Not a logic failure: Gemini returned HTTP 503 on the planner, the circuit breaker opened and the app degraded honestly (deterministic checks only, no hypotheses). Needs a re-run when the API is healthy. |

Not yet recorded: missing_policy_page, no_exif, poison_pill, unreadable, scanned_estimate, swapped_image. Raw output: `_lab_run.json` (gitignored), `/tmp/lab.log`.

## Limits
- Free-tier Gemini rate-limits and 503s; failures from those are degradation, not pipeline correctness.
- One run each; no latency distribution. Synthetic, labelled evidence only.
- The AI never denies claims, scores fraud or releases payment; a human approves.
