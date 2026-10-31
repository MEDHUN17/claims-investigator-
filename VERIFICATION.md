# Verity — verification (measured 31 Oct 2026, cloud Linux sandbox)

Everything below is a real run on live Gemini (10 rotating keys). Nothing is estimated. Sample size is tiny (one run per scenario, synthetic evidence) — treat as a smoke test, not a benchmark.

## Commands and results
| Command | Result |
|---|---|
| `cd backend && .venv/bin/python -m pytest -q` | 78 passed |
| `python scripts/e2e_check.py` (live) | 19/20 passed; the one failure ("data-error hypothesis present") was a real bug, fixed in `722b4a3`; e2e not re-run since |
| `python scripts/run_lab.py` (live, one scenario at a time) | 5 of 10 scenarios passed, see below |

e2e values observed: quoted total 35700.00, recomputed 35700.00, proposed settlement 22300.00, 5/5 gates pass, report.pdf 11,013 bytes.

## Proof Lab (all 10 scenarios, one run each, live Gemini, `python scripts/run_lab.py`)
**5 of 10 passed.** Of the 5 that failed, 4 are Gemini outage degradations and 1 is a real model-behaviour result.

| Scenario | Result | Assertions | Latency | Note |
|---|---|---|---|---|
| consistent | PASS | 9/9 | 39 s | |
| rear_vs_front | PASS | 9/9 | 15 s | |
| twist_secondary_impact | FAIL | 8/9 | 82 s | Real result. Stale re-open worked (F-01, F-02, F-Z1 went stale on the new evidence) but the model added no new finding ids, so "At least 1 finding added" got 0. `fixtures/twist_secondary_impact/expected.json` (`delta.added_min: 1`) may be too strict; left unedited for the owner to decide. |
| bad_estimate | FAIL | 7/8 | 13 s | Outage: planner got HTTP 503, circuit breaker opened, app degraded honestly (deterministic checks only, 0 hypotheses). |
| missing_policy_page | FAIL | 7/8 | 10 s | Outage, same cause (0 hypotheses, "AI analysis unavailable"). |
| no_exif | FAIL | 7/8 | 11 s | Outage, same cause. |
| poison_pill | FAIL | 6/7 | 11 s | Outage, same cause. |
| unreadable | PASS | 6/6 | 19 s | |
| scanned_estimate | PASS | 6/6 | 41 s | |
| swapped_image | PASS | 2/2 | 47 s | |

The 4 outage failures must be re-run when the Gemini planner models are healthy; until then they say nothing about the baseline-hypothesis fix. Raw output: `_lab_run.json` (gitignored).

## Limits
- Free-tier Gemini rate-limits and 503s; failures from those are degradation, not pipeline correctness.
- One run each; no latency distribution. Synthetic, labelled evidence only.
- The AI never denies claims, scores fraud or releases payment; a human approves.
