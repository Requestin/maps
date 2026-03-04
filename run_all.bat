@echo off
cd /d "C:\Cursor Projects\maps"

REM Окно 1: FastAPI
start "uvicorn" cmd /k ".venv\Scripts\activate && uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload"

REM Окно 2: Celery worker
start "celery-worker" cmd /k ".venv\Scripts\activate && celery -A backend.app.celery_app worker --loglevel=debug --pool=solo"

REM Окно 3: Celery beat (опционально)
start "celery-beat" cmd /k ".venv\Scripts\activate && celery -A backend.app.celery_app beat --loglevel=info"