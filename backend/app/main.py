"""FastAPI приложение: создание app, middleware, раздача статики, логирование."""

import sys
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger

from backend.app.config import BASE_DIR, LOG_DIR, LOG_FORMAT, LOG_LEVEL, LOG_RETENTION, LOG_ROTATION

# --- Настройка loguru ---
logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL, format=LOG_FORMAT, colorize=True)
logger.add(
    str(LOG_DIR / "mapvideo_{time:YYYY-MM-DD}.log"),
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    rotation=LOG_ROTATION,
    retention=LOG_RETENTION,
    encoding="utf-8",
)
logger.info("=== MapVideo сервис запускается ===")
logger.info("BASE_DIR={}", BASE_DIR)
logger.info("LOG_DIR={}", LOG_DIR)

# --- FastAPI app ---
app = FastAPI(
    title="MapVideo",
    description="Сервис генерации видео с анимированными картами",
    version="1.0.0-mvp",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    session_id = request.headers.get("X-Session-ID", "no-session")

    logger.info(
        "→ {} {} (session={})",
        request.method, request.url.path, session_id,
    )

    response = await call_next(request)

    elapsed = time.perf_counter() - start
    logger.info(
        "← {} {} → {} ({:.0f}мс)",
        request.method, request.url.path, response.status_code, elapsed * 1000,
    )
    return response


# --- Роуты API ---
from backend.app.api.routes import router as api_router  # noqa: E402

app.include_router(api_router)

# --- Статика (фронтенд) ---
frontend_dir = BASE_DIR / "frontend"
if frontend_dir.exists():
    app.mount("/css", StaticFiles(directory=str(frontend_dir / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(frontend_dir / "js")), name="js")

    @app.get("/")
    async def serve_index():
        return FileResponse(str(frontend_dir / "index.html"))

    logger.info("Фронтенд подключён: {}", frontend_dir)
else:
    logger.warning("Директория фронтенда не найдена: {}", frontend_dir)
