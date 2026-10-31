# Verity / Claims Investigator

Synthetic motor-insurance claims investigation demo with a FastAPI backend,
PostgreSQL, and a React/Vite frontend. See `CLAUDE.md` for development rules,
`HANDOFF.md` for the demo flow and known limits, and `docs/SPEC.md` for the spec.

## Continue in a Linux cloud environment

From the repository root, create the Python environment and install the same
dependencies used by the Windows launcher:

```bash
python3 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install fastapi 'uvicorn[standard]' sqlalchemy 'psycopg[binary]' pydantic alembic python-multipart pypdf pillow reportlab httpx python-dotenv pixeltable-pgserver pypdfium2 rapidocr-onnxruntime imagehash rapidfuzz google-genai pytest
cp backend/.env.example backend/.env
```

Set `GEMINI_API_KEY` in the cloud environment's secret settings or in the ignored
`backend/.env` file. Leave `DATABASE_URL` blank to use bundled PostgreSQL, or set
it to a PostgreSQL connection URL. AI analysis needs a valid provider key and
network access. Never commit real keys or real claimant evidence.

Build the frontend, then start the API (which also serves the built UI):

```bash
cd frontend
npm ci
npm run build
cd ../backend
source .venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Use the environment's preview for port 8000. On Windows, build the frontend and
use `run.bat` instead. Run backend tests from `backend` with the environment
activated: `python -m pytest -q`.

## Presentation

The pitch deck (product tour with real screenshots, technical architecture, Proof Lab results and likely
judge questions) is at [`docs/presentation.pptx`](docs/presentation.pptx).

## Repository contents

Source code, tests, synthetic fixtures, documentation, and demo deck are included.
Local API keys, PostgreSQL data, uploaded evidence in `backend/storage`, virtual
environments, dependencies, generated frontend builds, and logs are ignored.
An environment cloned from GitHub starts with a fresh database; use the UI's
"Load demo case" action to load the synthetic fixtures.
