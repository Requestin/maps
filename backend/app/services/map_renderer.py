"""Сшивание тайлов в фоновое изображение, fallback тёмной темы, генерация кадров."""

import math
import time

import cv2
import numpy as np
from loguru import logger

from backend.app.config import (
    CAMERA_BREATH_AMPLITUDE,
    CAMERA_BREATH_CYCLES,
    CAMERA_BREATH_ENABLED,
    DARK_THEME_FALLBACK,
    TILE_SIZE,
    VIDEO_DURATION,
    VIDEO_FPS,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
)
from backend.app.services.animator import (
    apply_labels_overlay,
    create_labels_overlay,
    draw_dashed_line,
    draw_pulsating_marker,
)
from backend.app.services.tile_math import lat_lon_to_frame_pixel
from backend.app.services.video_encoder import VideoEncoder


def stitch_tiles(
    tiles: dict[tuple[int, int], np.ndarray],
    grid: dict,
) -> np.ndarray:
    """Сшить тайлы в одно фоновое изображение и обрезать до VIDEO_WIDTH x VIDEO_HEIGHT.

    Args:
        tiles: {(tile_x, tile_y): numpy_array_RGB}.
        grid: результат calc_tile_grid().

    Returns:
        numpy-массив BGR (VIDEO_HEIGHT, VIDEO_WIDTH, 3), dtype uint8.
    """
    start = time.perf_counter()

    cols = grid["cols"]
    rows = grid["rows"]
    full_w = cols * TILE_SIZE
    full_h = rows * TILE_SIZE

    canvas = np.zeros((full_h, full_w, 3), dtype=np.uint8)

    x_start = grid["tile_x_start"]
    y_start = grid["tile_y_start"]

    for ty in range(grid["tile_y_start"], grid["tile_y_end"] + 1):
        for tx in range(grid["tile_x_start"], grid["tile_x_end"] + 1):
            tile_rgb = tiles.get((tx, ty))
            if tile_rgb is None:
                continue
            if tile_rgb.shape[:2] != (TILE_SIZE, TILE_SIZE):
                tile_rgb = cv2.resize(tile_rgb, (TILE_SIZE, TILE_SIZE))

            col = tx - x_start
            row = ty - y_start
            y1 = row * TILE_SIZE
            x1 = col * TILE_SIZE
            canvas[y1:y1 + TILE_SIZE, x1:x1 + TILE_SIZE] = tile_rgb

    ox = grid["offset_x"]
    oy = grid["offset_y"]
    cropped = canvas[oy:oy + VIDEO_HEIGHT, ox:ox + VIDEO_WIDTH]

    background = cv2.cvtColor(cropped, cv2.COLOR_RGB2BGR)

    elapsed = time.perf_counter() - start
    logger.info(
        "stitch_tiles: сшито {}x{} → кроп {}x{} за {:.3f}с",
        full_w, full_h, background.shape[1], background.shape[0], elapsed,
    )
    return background


def apply_dark_theme_fallback(image: np.ndarray) -> np.ndarray:
    """Постобработка: стандартные тайлы → тёмная тема через HSV-инверсию."""
    start = time.perf_counter()

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
    h, s, v = cv2.split(hsv)
    v = 255.0 - v
    v = np.clip(v * 0.7, 0, 255)
    s = np.clip(s * 0.6, 0, 255)
    dark_hsv = cv2.merge([h, s.astype(np.float32), v.astype(np.float32)]).astype(np.uint8)
    result = cv2.cvtColor(dark_hsv, cv2.COLOR_HSV2BGR)

    elapsed = time.perf_counter() - start
    logger.info("apply_dark_theme_fallback: инверсия за {:.3f}с", elapsed)
    return result


def generate_video(
    output_path: str,
    background: np.ndarray,
    cities: list[dict],
    grid: dict,
    zoom: int,
    progress_callback=None,
) -> dict:
    """Сгенерировать MP4-видео: кадры с анимацией поверх фонового изображения карты.

    Args:
        output_path: путь к выходному MP4 файлу.
        background: BGR-изображение фона (VIDEO_HEIGHT x VIDEO_WIDTH x 3).
        cities: [{"name": str, "lat": float, "lon": float}, ...].
        grid: результат calc_tile_grid().
        zoom: zoom-уровень карты.
        progress_callback: callable(current_frame, total_frames) — для обновления прогресса.

    Returns:
        dict от VideoEncoder.finish().
    """
    total_frames = VIDEO_FPS * VIDEO_DURATION
    logger.info(
        "generate_video: {} кадров ({}с @ {}fps), {} городов, вывод: {}",
        total_frames, VIDEO_DURATION, VIDEO_FPS, len(cities), output_path,
    )

    city_pixels = []
    for c in cities:
        fx, fy = lat_lon_to_frame_pixel(c["lat"], c["lon"], zoom, grid)
        city_pixels.append({"name": c["name"], "x": fx, "y": fy})
        logger.debug("Город '{}': пиксели ({}, {})", c["name"], fx, fy)

    labels_overlay = create_labels_overlay(city_pixels)

    encoder = VideoEncoder(output_path)
    encoder.start()

    gen_start = time.perf_counter()

    breath_on = CAMERA_BREATH_ENABLED and CAMERA_BREATH_AMPLITUDE > 0 and CAMERA_BREATH_CYCLES > 0
    if breath_on:
        logger.info(
            "Дыхание камеры: cycles={}, amplitude={:.3f}",
            CAMERA_BREATH_CYCLES, CAMERA_BREATH_AMPLITUDE,
        )

    for i in range(total_frames):
        t = i / VIDEO_FPS
        frame = background.copy()

        for cp in city_pixels:
            draw_pulsating_marker(frame, (cp["x"], cp["y"]), t)

        if len(city_pixels) == 2:
            pt_a = (city_pixels[0]["x"], city_pixels[0]["y"])
            pt_b = (city_pixels[1]["x"], city_pixels[1]["y"])
            draw_dashed_line(frame, pt_a, pt_b, t)

        apply_labels_overlay(frame, labels_overlay)

        if breath_on:
            norm = t / VIDEO_DURATION if VIDEO_DURATION > 0 else 0.0
            phase = 2.0 * math.pi * CAMERA_BREATH_CYCLES * norm
            scale = 1.0 + CAMERA_BREATH_AMPLITUDE * (0.5 + 0.5 * math.sin(phase))

            if scale > 1.001:
                new_w = int(VIDEO_WIDTH * scale)
                new_h = int(VIDEO_HEIGHT * scale)
                resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
                x0 = (new_w - VIDEO_WIDTH) // 2
                y0 = (new_h - VIDEO_HEIGHT) // 2
                frame = resized[y0:y0 + VIDEO_HEIGHT, x0:x0 + VIDEO_WIDTH]

        encoder.write_frame(frame)

        if (i + 1) % VIDEO_FPS == 0:
            sec = (i + 1) // VIDEO_FPS
            elapsed = time.perf_counter() - gen_start
            avg_ms = elapsed / (i + 1) * 1000
            logger.info(
                "Генерация кадров: {}/{} (секунда {}/{}), avg {:.1f} мс/кадр",
                i + 1, total_frames, sec, VIDEO_DURATION, avg_ms,
            )

        if progress_callback and (i + 1) % 30 == 0:
            progress_callback(i + 1, total_frames)

    result = encoder.finish()
    total_elapsed = time.perf_counter() - gen_start
    logger.info("generate_video: полная генерация за {:.2f}с", total_elapsed)

    return result
