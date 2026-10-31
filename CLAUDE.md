# Verity (TCS Challenge 08) — project notes

Run: `run.bat` (starts API + built UI at http://127.0.0.1:8000; first start boots the bundled PostgreSQL 16 under `.pgdata`, ~10 s). UI build: `cd frontend && npm run build`. Tests: `cd backend && .venv\Scripts\python.exe -m pytest -q`.
Layout: `backend/app` (contracts.py = data contract; pipeline/extract/analyze/validate/calc/invalidate/gates = AI + deterministic core; providers.py = Gemini failover; repo/jobs/api_* = plumbing), `frontend/src` (types.ts mirrors contracts.py), `fixtures` (synthetic packs + expected.json), `docs/SPEC.md`, `docs/EXPLAIN_IT.md`.
Rules: free-only; synthetic evidence only; AI never denies, scores fraud or releases payment; amounts are decimal strings; every quote/amount must be found in source text (receipts); no canned findings in app paths (fakes only in tests); never print or commit backend/.env (GEMINI_API_KEY; extra keys GEMINI_API_KEY_2..9 rotate on 429).
Gemini: readers use lite models, planner uses 3.6/3.5/3-flash-preview/3.8 (3.8 and 3.7 time out under load). Free tier rate-limits (429/503); the app degrades honestly and says so.
