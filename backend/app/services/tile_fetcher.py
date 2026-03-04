"""Загрузка тайлов Яндекс Tiles API: параллельная, с ретраями и логированием."""

import asyncio
import io
import time

import aiohttp
import numpy as np
from PIL import Image
from loguru import logger

from backend.app.config import (
    TILE_DOWNLOAD_TIMEOUT,
    TILE_MAX_RETRIES,
    TILE_RETRY_DELAY,
    TILE_SIZE,
    YANDEX_API_KEY,
    YANDEX_TILE_URL,
)


def _build_tile_url(x: int, y: int, z: int) -> str:
    return YANDEX_TILE_URL.format(x=x, y=y, z=z, apikey=YANDEX_API_KEY)


async def _fetch_single_tile(
    session: aiohttp.ClientSession,
    x: int, y: int, z: int,
    semaphore: asyncio.Semaphore,
) -> tuple[int, int, np.ndarray | None]:
    """Загрузить один тайл с ретраями.

    Returns:
        (x, y, numpy_array_RGB | None)
    """
    url = _build_tile_url(x, y, z)

    for attempt in range(1, TILE_MAX_RETRIES + 1):
        start = time.perf_counter()
        try:
            async with semaphore:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=TILE_DOWNLOAD_TIMEOUT),
                ) as resp:
                    elapsed = time.perf_counter() - start
                    status = resp.status

                    if status == 200:
                        data = await resp.read()
                        logger.debug(
                            "Тайл ({},{}) z={}: HTTP {}, {} байт, {:.2f}с",
                            x, y, z, status, len(data), elapsed,
                        )
                        img = Image.open(io.BytesIO(data)).convert("RGB")
                        return x, y, np.array(img)

                    logger.warning(
                        "Тайл ({},{}) z={}: HTTP {} (попытка {}/{}), {:.2f}с",
                        x, y, z, status, attempt, TILE_MAX_RETRIES, elapsed,
                    )

        except Exception as exc:
            elapsed = time.perf_counter() - start
            logger.warning(
                "Тайл ({},{}) z={}: ошибка '{}' (попытка {}/{}), {:.2f}с",
                x, y, z, exc, attempt, TILE_MAX_RETRIES, elapsed,
            )

        if attempt < TILE_MAX_RETRIES:
            await asyncio.sleep(TILE_RETRY_DELAY)

    logger.error("Тайл ({},{}) z={}: все {} попыток неудачны", x, y, z, TILE_MAX_RETRIES)
    return x, y, None


async def fetch_tiles(grid: dict) -> dict[tuple[int, int], np.ndarray]:
    """Загрузить все тайлы для заданной сетки.

    Args:
        grid: результат calc_tile_grid() из tile_math.

    Returns:
        Словарь {(tile_x, tile_y): numpy_array_RGB}.

    Raises:
        RuntimeError: если хотя бы один тайл не удалось загрузить.
    """
    zoom = grid["zoom"]
    x_start = grid["tile_x_start"]
    y_start = grid["tile_y_start"]
    x_end = grid["tile_x_end"]
    y_end = grid["tile_y_end"]

    tasks_list = []
    total = grid["cols"] * grid["rows"]
    logger.info(
        "fetch_tiles: загрузка {} тайлов (x: {}..{}, y: {}..{}, zoom={})",
        total, x_start, x_end, y_start, y_end, zoom,
    )

    semaphore = asyncio.Semaphore(20)
    start_all = time.perf_counter()

    async with aiohttp.ClientSession() as session:
        for ty in range(y_start, y_end + 1):
            for tx in range(x_start, x_end + 1):
                tasks_list.append(_fetch_single_tile(session, tx, ty, zoom, semaphore))

        results = await asyncio.gather(*tasks_list)

    elapsed_all = time.perf_counter() - start_all
    tiles: dict[tuple[int, int], np.ndarray] = {}
    failed = 0

    for x, y, arr in results:
        if arr is not None:
            tiles[(x, y)] = arr
        else:
            failed += 1

    logger.info(
        "fetch_tiles: загружено {}/{} тайлов за {:.2f}с, failed={}",
        len(tiles), total, elapsed_all, failed,
    )

    if failed > 0:
        raise RuntimeError(f"Не удалось загрузить {failed} из {total} тайлов")

    return tiles


def fetch_tiles_sync(grid: dict) -> dict[tuple[int, int], np.ndarray]:
    """Синхронная обёртка для fetch_tiles (для вызова из Celery worker)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, fetch_tiles(grid))
            return future.result()
    else:
        return asyncio.run(fetch_tiles(grid))
