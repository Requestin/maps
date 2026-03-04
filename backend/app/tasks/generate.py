"""Celery-задача: полный пайплайн генерации видео."""

import json
import time
from datetime import datetime, timezone

import redis as redis_lib
from loguru import logger

from backend.app.celery_app import app as celery_app
from backend.app.config import (
    DARK_THEME_FALLBACK,
    REDIS_URL,
    VIDEO_OUTPUT_DIR,
    VIDEO_TTL_DAYS,
)
from backend.app.api.dependencies import decrement_queue
from backend.app.services.geocoder import geocode_city
from backend.app.services.map_renderer import (
    apply_dark_theme_fallback,
    generate_video,
    stitch_tiles,
)
from backend.app.services.tile_fetcher import fetch_tiles_sync
from backend.app.services.tile_math import (
    calc_tile_grid,
    calc_zoom_for_single_city,
    calc_zoom_for_two_cities,
)

_redis = redis_lib.Redis.from_url(REDIS_URL, decode_responses=True)
_TTL_SECONDS = VIDEO_TTL_DAYS * 86400


def _update_task(task_id: str, **fields) -> None:
    """Обновить поля задачи в Redis."""
    key = f"task:{task_id}"
    _redis.hset(key, mapping={k: str(v) for k, v in fields.items()})
    _redis.expire(key, _TTL_SECONDS)


@celery_app.task(name="backend.app.tasks.generate.generate_video_task", bind=True)
def generate_video_task(self, task_id: str, mode: str, cities_json: str) -> dict:
    """Полный пайплайн: геокодирование → тайлы → рендеринг → видео."""
    cities_input = json.loads(cities_json)
    logger.info("=== ЗАДАЧА {} СТАРТ === mode={}, cities={}", task_id, mode, cities_input)

    _update_task(task_id, status="processing", progress="Геокодирование...")

    try:
        pipeline_start = time.perf_counter()

        # --- Шаг 1: Геокодирование ---
        geocoded = []
        for city_name in cities_input:
            lat, lon = geocode_city(city_name)
            geocoded.append({"name": city_name, "lat": lat, "lon": lon})

        logger.info("Геокодирование завершено: {}", geocoded)
        _update_task(task_id, progress="Расчёт карты...")

        # --- Шаг 2: Zoom и центр ---
        if mode == "single":
            lat, lon = geocoded[0]["lat"], geocoded[0]["lon"]
            zoom = calc_zoom_for_single_city(lat)
            center_lat, center_lon = lat, lon
        else:
            zoom, center_lat, center_lon = calc_zoom_for_two_cities(
                geocoded[0]["lat"], geocoded[0]["lon"],
                geocoded[1]["lat"], geocoded[1]["lon"],
            )

        # --- Шаг 3: Сетка тайлов ---
        grid = calc_tile_grid(center_lat, center_lon, zoom)

        # --- Шаг 4: Загрузка тайлов ---
        _update_task(task_id, progress="Загрузка тайлов...")
        tiles = fetch_tiles_sync(grid)

        # --- Шаг 5: Сшивание фона ---
        _update_task(task_id, progress="Сборка карты...")
        background = stitch_tiles(tiles, grid)

        if DARK_THEME_FALLBACK:
            background = apply_dark_theme_fallback(background)

        # --- Шаг 6: Генерация видео ---
        output_path = str(VIDEO_OUTPUT_DIR / f"{task_id}.mp4")

        def on_progress(current: int, total: int) -> None:
            _update_task(task_id, progress=f"Генерация кадров: {current}/{total}")

        _update_task(task_id, progress="Генерация видео...")
        result = generate_video(
            output_path=output_path,
            background=background,
            cities=geocoded,
            grid=grid,
            zoom=zoom,
            progress_callback=on_progress,
        )

        if result["return_code"] != 0:
            raise RuntimeError(f"FFmpeg завершился с кодом {result['return_code']}")

        pipeline_elapsed = time.perf_counter() - pipeline_start
        now = datetime.now(timezone.utc).isoformat()

        _update_task(
            task_id,
            status="completed",
            progress="",
            completed_at=now,
            video_url=f"/api/download/{task_id}",
        )

        logger.info(
            "=== ЗАДАЧА {} ЗАВЕРШЕНА === {:.2f}с, файл={}, {} байт",
            task_id, pipeline_elapsed, output_path, result["file_size"],
        )
        return {"status": "completed", "elapsed": pipeline_elapsed}

    except Exception as exc:
        logger.exception("=== ЗАДАЧА {} ОШИБКА === {}", task_id, exc)
        _update_task(task_id, status="failed", error=str(exc), progress="")
        return {"status": "failed", "error": str(exc)}

    finally:
        decrement_queue()
