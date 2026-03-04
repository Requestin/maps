"""Celery-задача: автоочистка старых видео."""

import time
from pathlib import Path

from loguru import logger

from backend.app.celery_app import app as celery_app
from backend.app.config import VIDEO_OUTPUT_DIR, VIDEO_TTL_DAYS


@celery_app.task(name="backend.app.tasks.cleanup.cleanup_old_videos")
def cleanup_old_videos() -> dict:
    """Удалить MP4-файлы старше VIDEO_TTL_DAYS дней."""
    logger.info("cleanup_old_videos: запуск, директория={}, TTL={} дней", VIDEO_OUTPUT_DIR, VIDEO_TTL_DAYS)

    now = time.time()
    max_age = VIDEO_TTL_DAYS * 86400
    checked = 0
    deleted = 0
    freed_bytes = 0

    video_dir = Path(VIDEO_OUTPUT_DIR)
    if not video_dir.exists():
        logger.info("cleanup_old_videos: директория не существует, ничего не делаем")
        return {"checked": 0, "deleted": 0, "freed_bytes": 0}

    for f in video_dir.glob("*.mp4"):
        checked += 1
        try:
            age = now - f.stat().st_mtime
            if age > max_age:
                size = f.stat().st_size
                f.unlink()
                deleted += 1
                freed_bytes += size
                logger.debug("Удалён: {} ({} байт, возраст {:.0f}ч)", f.name, size, age / 3600)
        except OSError as exc:
            logger.warning("Ошибка при удалении {}: {}", f.name, exc)

    logger.info(
        "cleanup_old_videos: проверено={}, удалено={}, освобождено={:.1f} МБ",
        checked, deleted, freed_bytes / 1024 / 1024,
    )
    return {"checked": checked, "deleted": deleted, "freed_bytes": freed_bytes}
