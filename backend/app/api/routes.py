"""API-эндпоинты: generate, status, tasks, download, queue/info."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import redis as redis_lib
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from loguru import logger

from backend.app.api.dependencies import (
    check_queue_not_full,
    get_redis,
    get_session_id,
    increment_queue,
)
from backend.app.config import MAX_QUEUE_SIZE, VIDEO_OUTPUT_DIR, VIDEO_TTL_DAYS
from backend.app.models.schemas import (
    ErrorResponse,
    GenerateRequest,
    GenerateResponse,
    QueueInfoResponse,
    TaskListResponse,
    TaskStatus,
)
from backend.app.tasks.generate import generate_video_task

router = APIRouter(prefix="/api")


def _handle_redis_error(exc: redis_lib.exceptions.ConnectionError):
    logger.error("Redis недоступен: {}", exc)
    return JSONResponse(
        status_code=503,
        content={"error": "Сервис временно недоступен (Redis не подключён). Убедитесь, что Redis запущен."},
    )

_TTL_SECONDS = VIDEO_TTL_DAYS * 86400


@router.post(
    "/generate",
    response_model=GenerateResponse,
    status_code=201,
    responses={429: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
def create_task(
    body: GenerateRequest,
    session_id: str = Depends(get_session_id),
):
    logger.info("POST /api/generate: session={}, mode={}, body={}", session_id, body.mode, body.model_dump())

    if body.mode == "single":
        if not body.city:
            raise HTTPException(status_code=400, detail="Не указан город")
        cities = [body.city.strip()]
    else:
        if not body.city_a or not body.city_b:
            raise HTTPException(status_code=400, detail="Не указаны оба города")
        cities = [body.city_a.strip(), body.city_b.strip()]

    try:
        check_queue_not_full()
    except redis_lib.exceptions.ConnectionError as exc:
        return _handle_redis_error(exc)

    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    try:
        r = get_redis()
    except redis_lib.exceptions.ConnectionError as exc:
        return _handle_redis_error(exc)

    task_data = {
        "session_id": session_id,
        "mode": body.mode,
        "cities": json.dumps(cities, ensure_ascii=False),
        "status": "queued",
        "progress": "",
        "error": "",
        "video_url": "",
        "created_at": now,
        "completed_at": "",
    }
    r.hset(f"task:{task_id}", mapping=task_data)
    r.expire(f"task:{task_id}", _TTL_SECONDS)

    r.sadd(f"session:{session_id}:tasks", task_id)
    r.expire(f"session:{session_id}:tasks", _TTL_SECONDS)

    increment_queue()

    generate_video_task.apply_async(
        args=[task_id, body.mode, json.dumps(cities, ensure_ascii=False)],
        task_id=task_id,
        link_error=None,
    )

    active = r.get("queue:active_count")
    position = int(active) if active else 1

    logger.info("Задача {} создана, позиция в очереди: {}", task_id, position)
    return GenerateResponse(task_id=task_id, status="queued", position=position)


@router.get("/status/{task_id}", response_model=TaskStatus)
def get_task_status(
    task_id: str,
    session_id: str = Depends(get_session_id),
):
    try:
        r = get_redis()
        data = r.hgetall(f"task:{task_id}")
    except redis_lib.exceptions.ConnectionError as exc:
        return _handle_redis_error(exc)

    if not data:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    if data.get("session_id") != session_id:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    cities = json.loads(data.get("cities", "[]"))

    return TaskStatus(
        task_id=task_id,
        status=data.get("status", "unknown"),
        mode=data.get("mode"),
        cities=cities,
        progress=data.get("progress") or None,
        error=data.get("error") or None,
        video_url=data.get("video_url") or None,
        created_at=data.get("created_at") or None,
        completed_at=data.get("completed_at") or None,
    )


@router.get("/tasks", response_model=TaskListResponse)
def get_user_tasks(
    session_id: str = Depends(get_session_id),
):
    try:
        r = get_redis()
        task_ids = r.smembers(f"session:{session_id}:tasks")
    except redis_lib.exceptions.ConnectionError as exc:
        return _handle_redis_error(exc)

    tasks = []
    for tid in sorted(task_ids, reverse=True):
        data = r.hgetall(f"task:{tid}")
        if not data:
            continue
        cities = json.loads(data.get("cities", "[]"))
        tasks.append(TaskStatus(
            task_id=tid,
            status=data.get("status", "unknown"),
            mode=data.get("mode"),
            cities=cities,
            progress=data.get("progress") or None,
            error=data.get("error") or None,
            video_url=data.get("video_url") or None,
            created_at=data.get("created_at") or None,
            completed_at=data.get("completed_at") or None,
        ))

    logger.debug("GET /api/tasks: session={}, tasks={}", session_id, len(tasks))
    return TaskListResponse(tasks=tasks)


@router.get("/download/{task_id}")
def download_video(
    task_id: str,
    sid: str | None = None,
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
):
    session_id = sid or x_session_id or ""
    if not session_id:
        raise HTTPException(status_code=400, detail="Не указан session_id")
    try:
        r = get_redis()
        data = r.hgetall(f"task:{task_id}")
    except redis_lib.exceptions.ConnectionError as exc:
        return _handle_redis_error(exc)

    if not data:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    if data.get("session_id") != session_id:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    if data.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Видео ещё не готово")

    file_path = Path(VIDEO_OUTPUT_DIR) / f"{task_id}.mp4"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Файл видео не найден")

    logger.debug("Отдаём видео: {}", file_path)
    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        filename=f"mapvideo_{task_id[:8]}.mp4",
    )


@router.get("/queue/info", response_model=QueueInfoResponse)
def queue_info():
    try:
        r = get_redis()
        active = r.get("queue:active_count")
        count = int(active) if active else 0
        count = max(0, count)
    except redis_lib.exceptions.ConnectionError as exc:
        return _handle_redis_error(exc)
    return QueueInfoResponse(queue_size=count, max_queue_size=MAX_QUEUE_SIZE)
