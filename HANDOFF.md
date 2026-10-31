# Verity — handoff

Project: `D:\claude code\claims-investigator`   Launch: `run.bat`  ->  http://127.0.0.1:8000  (API + built UI on one origin; first start ~10 s while the bundled PostgreSQL 16 boots; data in `.pgdata`).
Rebuild UI after frontend edits: `cd frontend && npm run build`. Reload demo data: UI Queue -> "Load demo case", or `backend\.venv\Scripts\python.exe scripts\demo_loader.py rear_vs_front`.
Secrets: `backend/.env` holds the Gemini key (git-ignored). The key was pasted in chat: ROTATE IT after the event and delete `backend/.env` before sharing the folder. Optional capacity boost: add `GEMINI_API_KEY_2=...` (another free project) and/or `GROQ_API_KEY=`.

## What was verified (commands and results are in VERIFICATION.md)
- Live end-to-end on the real stack (PostgreSQL 16.14, real Gemini): rear-impact case -> analysis -> human approval -> new evidence -> stale diff -> approval voided -> gates -> PDF. 20/20 checks in `scripts/e2e_check.py`.
- Backend unit/integration tests (pytest). Frontend `tsc` + production build. Browser walk-through of every screen on real data.
## What is NOT verified / known limits
- Free-tier Gemini is rate-limited and sometimes overloaded (429/503); the app fails over between models/keys and shows "AI analysis unavailable" with deterministic results only. A live demo can still hit this.
- Evidence is synthetic; photos are AI-generated and labelled. Scenario expectations are team-written, so results show regression/consistency checks, not field accuracy.
- Reviewer name is a typed label, not authentication. No Tamil/Hindi, audio/video analysis, or region boxes. Weather lookup runs only when the narrative gives date and coordinates.
- Docker packaging not built. SQLite fallback not wired (Postgres is bundled via the `pixeltable-pgserver` wheel).
## Supported inputs
png/jpg/webp photos; PDF (embedded text, OCR fallback via pypdfium2 + RapidOCR for scans); txt/md/csv/json. Audio/video/zip/unknown are stored with status "unsupported" and a request is created. Max 25 MB.
## Policy constructs handled (synthetic Indian motor policy; terms always read from the uploaded policy)
IDV cap; compulsory + voluntary deductible; depreciation by material (rubber/plastic/battery, fibre, glass nil) and metal by vehicle age in completed months (age from date of first registration and date of loss); exclusions (e.g. consumables); labour/paint not depreciated. Any missing or ambiguous term leaves the settlement UNRESOLVED and creates a request.
## Demo path (3 minutes)
1. Queue -> Load demo case "rear-strike vs front damage" (~1 min). 2. Evidence desk: original beside facts with receipts. 3. Investigation: Hypothesis Board (benign explanation present), ranked next-evidence request, blueprint rings show the rear-vs-front mismatch. 4. Review: waterfall, Approve (sealed to the revision hash). 5. Drop `fixtures/twist_secondary_impact/garage_report.pdf` (and witness_statement.txt): only dependants go stale, cited diff, request scored, approval flips to VOID. 6. Proof Lab: gates on this upload.
Reset: `POST /api/demo/reset` (deletes only demo-flagged cases).
