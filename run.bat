@echo off
setlocal
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" (
  echo [verity] creating virtual environment...
  python -m venv .venv || (echo [verity] python not found & exit /b 1)
)
call ".venv\Scripts\activate.bat"
python -c "import fastapi, uvicorn, sqlalchemy, psycopg, pixeltable_pgserver, alembic, reportlab" 2>nul
if errorlevel 1 (
  echo [verity] installing dependencies...
  python -m pip install --quiet fastapi "uvicorn[standard]" sqlalchemy "psycopg[binary]" pydantic alembic python-multipart pypdf pillow reportlab httpx python-dotenv pixeltable-pgserver pypdfium2 rapidocr-onnxruntime imagehash rapidfuzz google-genai pytest || exit /b 1
)
if not exist "..\frontend\dist\index.html" (
  echo [verity] note: frontend\dist not built - API only. Build with: cd frontend ^&^& npm run build
)
echo [verity] starting on http://127.0.0.1:8000  ^(first start boots the bundled PostgreSQL, ~10 s^)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
endlocal
