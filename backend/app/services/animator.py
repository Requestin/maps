"""Логика анимации: пульсирующий маркер, движущаяся пунктирная линия, подписи городов."""

import math

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from loguru import logger

from backend.app.config import (
    ATTRIBUTION_COLOR_RGB,
    ATTRIBUTION_FONT_SIZE,
    ATTRIBUTION_MARGIN,
    ATTRIBUTION_TEXT,
    DASH_GAP,
    DASH_LENGTH,
    DASH_SPEED,
    LABEL_COLOR_RGB,
    LABEL_FONT_PATH,
    LABEL_FONT_SIZE,
    LABEL_OFFSET_X,
    LABEL_OFFSET_Y,
    LABEL_OUTLINE_COLOR_RGB,
    LABEL_OUTLINE_WIDTH,
    LINE_COLOR_BGR,
    LINE_THICKNESS,
    MARKER_ALPHA_MAX,
    MARKER_ALPHA_MIN,
    MARKER_BASE_RADIUS,
    MARKER_COLOR_BGR,
    MARKER_PULSE_AMPLITUDE,
    PULSE_FREQUENCY,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
)


def draw_pulsating_marker(
    frame: np.ndarray,
    center: tuple[int, int],
    t: float,
) -> None:
    """Нарисовать пульсирующий красный маркер на кадре (in-place, с alpha-blending)."""
    phase = math.sin(2 * math.pi * PULSE_FREQUENCY * t)
    radius = int(MARKER_BASE_RADIUS + MARKER_PULSE_AMPLITUDE * phase)
    radius = max(3, radius)
    alpha = MARKER_ALPHA_MIN + (MARKER_ALPHA_MAX - MARKER_ALPHA_MIN) * (0.5 + 0.5 * phase)

    overlay = frame.copy()
    cv2.circle(overlay, center, radius, MARKER_COLOR_BGR, -1, cv2.LINE_AA)
    cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0, frame)


def draw_dashed_line(
    frame: np.ndarray,
    pt_a: tuple[int, int],
    pt_b: tuple[int, int],
    t: float,
) -> None:
    """Нарисовать движущуюся пунктирную линию от A к B."""
    ax, ay = pt_a
    bx, by = pt_b
    dx = bx - ax
    dy = by - ay
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1:
        return

    pattern_len = DASH_LENGTH + DASH_GAP
    offset = (t * DASH_SPEED) % pattern_len

    ux = dx / length
    uy = dy / length

    pos = -offset
    while pos < length:
        seg_start = max(pos, 0)
        seg_end = min(pos + DASH_LENGTH, length)
        if seg_end > seg_start:
            x1 = int(ax + ux * seg_start)
            y1 = int(ay + uy * seg_start)
            x2 = int(ax + ux * seg_end)
            y2 = int(ay + uy * seg_end)
            cv2.line(frame, (x1, y1), (x2, y2), LINE_COLOR_BGR, LINE_THICKNESS, cv2.LINE_AA)
        pos += pattern_len


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Загрузить TrueType шрифт с fallback на дефолтный."""
    try:
        font = ImageFont.truetype(LABEL_FONT_PATH, size)
        logger.debug("Шрифт загружен: {} (размер {})", LABEL_FONT_PATH, size)
        return font
    except (OSError, IOError) as exc:
        logger.warning("Не удалось загрузить шрифт '{}': {}. Используется дефолтный.", LABEL_FONT_PATH, exc)
        return ImageFont.load_default()


def create_labels_overlay(
    cities: list[dict],
) -> np.ndarray:
    """Создать RGBA-слой с подписями городов и атрибуцией Яндекса.

    Args:
        cities: список словарей [{"name": "Москва", "x": 960, "y": 540}, ...].

    Returns:
        numpy-массив (VIDEO_HEIGHT, VIDEO_WIDTH, 4), dtype uint8 (RGBA).
    """
    logger.debug("create_labels_overlay: {} городов", len(cities))

    img = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    label_font = _load_font(LABEL_FONT_SIZE)
    attr_font = _load_font(ATTRIBUTION_FONT_SIZE)

    for city in cities:
        name = city["name"]
        cx = city["x"] + LABEL_OFFSET_X
        cy = city["y"] + LABEL_OFFSET_Y

        for ox in range(-LABEL_OUTLINE_WIDTH, LABEL_OUTLINE_WIDTH + 1):
            for oy in range(-LABEL_OUTLINE_WIDTH, LABEL_OUTLINE_WIDTH + 1):
                if ox == 0 and oy == 0:
                    continue
                draw.text(
                    (cx + ox, cy + oy),
                    name,
                    font=label_font,
                    fill=(*LABEL_OUTLINE_COLOR_RGB, 255),
                )

        draw.text((cx, cy), name, font=label_font, fill=(*LABEL_COLOR_RGB, 255))
        logger.debug("Подпись '{}' размещена в ({}, {})", name, cx, cy)

    attr_bbox = draw.textbbox((0, 0), ATTRIBUTION_TEXT, font=attr_font)
    attr_w = attr_bbox[2] - attr_bbox[0]
    attr_h = attr_bbox[3] - attr_bbox[1]
    attr_x = VIDEO_WIDTH - attr_w - ATTRIBUTION_MARGIN
    attr_y = VIDEO_HEIGHT - attr_h - ATTRIBUTION_MARGIN

    for ox in range(-1, 2):
        for oy in range(-1, 2):
            if ox == 0 and oy == 0:
                continue
            draw.text((attr_x + ox, attr_y + oy), ATTRIBUTION_TEXT, font=attr_font, fill=(0, 0, 0, 200))
    draw.text((attr_x, attr_y), ATTRIBUTION_TEXT, font=attr_font, fill=(*ATTRIBUTION_COLOR_RGB, 255))

    return np.array(img)


def apply_labels_overlay(frame: np.ndarray, overlay_rgba: np.ndarray) -> None:
    """Наложить RGBA-слой подписей на BGR-кадр (in-place)."""
    alpha = overlay_rgba[:, :, 3].astype(np.float32) / 255.0
    overlay_bgr = overlay_rgba[:, :, :3][:, :, ::-1]

    mask = alpha > 0
    if not np.any(mask):
        return

    for c in range(3):
        frame_c = frame[:, :, c].astype(np.float32)
        over_c = overlay_bgr[:, :, c].astype(np.float32)
        frame[:, :, c] = np.where(
            mask,
            (frame_c * (1.0 - alpha) + over_c * alpha).astype(np.uint8),
            frame[:, :, c],
        )
