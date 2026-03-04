"""FastAPI dependencies: извлечение session_id, подключение к Redis, проверка очереди."""

from fastapi import Header, HTTPException
import redis as redis_lib
from loguru import logger

from backend.app.config import MAX_QUEUE_SIZE, REDIS_URL

_redis_client: redis_lib.Redis | None = None


def get_redis() -> redis_lib.Redis:
    """Получить (или создать) Redis-клиент."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis_lib.Redis.from_url(REDIS_URL, decode_responses=True)
        logger.debug("Redis-клиент создан: {}", REDIS_URL)
    return _redis_client


def get_session_id(x_session_id: str = Header(..., alias="X-Session-ID")) -> str:
    """Извлечь session_id из заголовка X-Session-ID."""
    if not x_session_id or len(x_session_id) < 8:
        raise HTTPException(status_code=400, detail="Не указан или некорректный X-Session-ID")
    return x_session_id


def check_queue_not_full() -> None:
    """Проверить, что очередь не переполнена."""
    r = get_redis()
    active_count = r.get("queue:active_count")
    count = int(active_count) if active_count else 0
    if count >= MAX_QUEUE_SIZE:
        logger.warning("Очередь переполнена: {}/{}", count, MAX_QUEUE_SIZE)
        raise HTTPException(
            status_code=429,
            detail="Очередь переполнена. Подождите, пожалуйста.",
        )


def increment_queue() -> None:
    r = get_redis()
    r.incr("queue:active_count")


def decrement_queue() -> None:
    r = get_redis()
    val = r.decr("queue:active_count")
    if val < 0:
        r.set("queue:active_count", 0)
