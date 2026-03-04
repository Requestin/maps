"""Конфигурация Celery + Redis."""

from celery import Celery

from backend.app.config import CLEANUP_INTERVAL_SECONDS, REDIS_URL

app = Celery(
    "mapvideo",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "backend.app.tasks.generate",
        "backend.app.tasks.cleanup",
    ],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_concurrency=1,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    beat_schedule={
        "cleanup-old-videos": {
            "task": "backend.app.tasks.cleanup.cleanup_old_videos",
            "schedule": CLEANUP_INTERVAL_SECONDS,
        },
    },
)
