"""Расчёт координат тайлов, zoom-уровня и bounding box.

Яндекс Карты используют эллиптическую проекцию Меркатора (EPSG:3395)
с эксцентриситетом WGS-84 ε = 0.0818191908426.
Источник: https://yandex.ru/dev/jsapi-v2-1/doc/ru/v2-1/theory/tiles
"""

import math

from loguru import logger

from backend.app.config import (
    SINGLE_CITY_RADIUS_KM,
    TILE_SIZE,
    TWO_CITY_PADDING_RATIO,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
)

WGS84_ECCENTRICITY = 0.0818191908426


def _elliptical_y_mercator(lat_rad: float) -> float:
    """Эллиптическая проекция Меркатора: ln(ρ(φ)) по формуле Яндекса.

    ρ(φ) = tan(π/4 + φ/2) · ((1 − ε·sin φ) / (1 + ε·sin φ))^(ε/2)
    """
    e = WGS84_ECCENTRICITY
    sin_lat = math.sin(lat_rad)
    rho = math.tan(math.pi / 4 + lat_rad / 2) * (
        (1 - e * sin_lat) / (1 + e * sin_lat)
    ) ** (e / 2)
    return math.log(rho)


def lat_lon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    """Конвертация (lat, lon) → (tile_x, tile_y) — эллиптический Меркатор."""
    n = 2 ** zoom
    tile_x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y_merc = _elliptical_y_mercator(lat_rad)
    tile_y = int((1.0 - y_merc / math.pi) / 2.0 * n)
    tile_x = max(0, min(tile_x, n - 1))
    tile_y = max(0, min(tile_y, n - 1))
    logger.debug(
        "lat_lon_to_tile: lat={}, lon={}, zoom={} -> tile_x={}, tile_y={}",
        lat, lon, zoom, tile_x, tile_y,
    )
    return tile_x, tile_y


def lat_lon_to_pixel(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Конвертация (lat, lon) → (pixel_x, pixel_y) — эллиптический Меркатор."""
    n = 2 ** zoom
    pixel_x = (lon + 180.0) / 360.0 * n * TILE_SIZE
    lat_rad = math.radians(lat)
    y_merc = _elliptical_y_mercator(lat_rad)
    pixel_y = (1.0 - y_merc / math.pi) / 2.0 * n * TILE_SIZE
    return pixel_x, pixel_y


def meters_per_pixel(lat: float, zoom: int) -> float:
    """Разрешение в метрах на пиксель на данной широте и zoom."""
    return 156543.03 * math.cos(math.radians(lat)) / (2 ** zoom)


def calc_zoom_for_single_city(lat: float, radius_km: float | None = None) -> int:
    """Подобрать zoom так, чтобы видимая область по горизонтали ≈ 2 * radius_km."""
    radius_km = radius_km or SINGLE_CITY_RADIUS_KM
    target_mpp = (radius_km * 2 * 1000) / VIDEO_WIDTH
    zoom = math.log2(156543.03 * math.cos(math.radians(lat)) / target_mpp)
    zoom = max(1, min(int(round(zoom)), 18))
    logger.info(
        "calc_zoom_for_single_city: lat={}, radius_km={}, target_mpp={:.2f} -> zoom={}",
        lat, radius_km, target_mpp, zoom,
    )
    return zoom


def calc_zoom_for_two_cities(
    lat_a: float, lon_a: float,
    lat_b: float, lon_b: float,
) -> tuple[int, float, float]:
    """Подобрать zoom и центр карты для двух городов.

    Returns:
        (zoom, center_lat, center_lon)
    """
    center_lat = (lat_a + lat_b) / 2
    center_lon = (lon_a + lon_b) / 2

    lat_min = min(lat_a, lat_b)
    lat_max = max(lat_a, lat_b)
    lon_min = min(lon_a, lon_b)
    lon_max = max(lon_a, lon_b)

    lat_span = lat_max - lat_min
    lon_span = lon_max - lon_min
    lat_min -= lat_span * TWO_CITY_PADDING_RATIO
    lat_max += lat_span * TWO_CITY_PADDING_RATIO
    lon_min -= lon_span * TWO_CITY_PADDING_RATIO
    lon_max += lon_span * TWO_CITY_PADDING_RATIO

    for z in range(18, 0, -1):
        px_min_x, px_min_y = lat_lon_to_pixel(lat_max, lon_min, z)
        px_max_x, px_max_y = lat_lon_to_pixel(lat_min, lon_max, z)
        width = abs(px_max_x - px_min_x)
        height = abs(px_max_y - px_min_y)
        if width <= VIDEO_WIDTH and height <= VIDEO_HEIGHT:
            logger.info(
                "calc_zoom_for_two_cities: ({},{}) - ({},{}) -> zoom={}, center=({},{}), "
                "bbox_px={}x{}",
                lat_a, lon_a, lat_b, lon_b, z,
                center_lat, center_lon, width, height,
            )
            return z, center_lat, center_lon

    logger.warning("calc_zoom_for_two_cities: fallback to zoom=1")
    return 1, center_lat, center_lon


def calc_tile_grid(
    center_lat: float, center_lon: float, zoom: int,
) -> dict:
    """Рассчитать сетку тайлов, необходимых для покрытия кадра VIDEO_WIDTH x VIDEO_HEIGHT.

    Returns:
        {
            "tile_x_start": int,
            "tile_y_start": int,
            "tile_x_end": int,   (inclusive)
            "tile_y_end": int,   (inclusive)
            "offset_x": int,     пиксельное смещение кропа от левого верхнего угла сетки тайлов
            "offset_y": int,
            "cols": int,
            "rows": int,
        }
    """
    center_px, center_py = lat_lon_to_pixel(center_lat, center_lon, zoom)

    left_px = center_px - VIDEO_WIDTH / 2
    top_py = center_py - VIDEO_HEIGHT / 2

    tile_x_start = int(left_px // TILE_SIZE)
    tile_y_start = int(top_py // TILE_SIZE)
    tile_x_end = int((left_px + VIDEO_WIDTH - 1) // TILE_SIZE)
    tile_y_end = int((top_py + VIDEO_HEIGHT - 1) // TILE_SIZE)

    offset_x = int(left_px - tile_x_start * TILE_SIZE)
    offset_y = int(top_py - tile_y_start * TILE_SIZE)

    cols = tile_x_end - tile_x_start + 1
    rows = tile_y_end - tile_y_start + 1

    result = {
        "tile_x_start": tile_x_start,
        "tile_y_start": tile_y_start,
        "tile_x_end": tile_x_end,
        "tile_y_end": tile_y_end,
        "offset_x": offset_x,
        "offset_y": offset_y,
        "cols": cols,
        "rows": rows,
        "zoom": zoom,
    }
    logger.debug(
        "calc_tile_grid: center=({},{}), zoom={} -> {} tiles ({}x{}), offset=({},{})",
        center_lat, center_lon, zoom, cols * rows, cols, rows, offset_x, offset_y,
    )
    return result


def lat_lon_to_frame_pixel(
    lat: float, lon: float, zoom: int, grid: dict,
) -> tuple[int, int]:
    """Конвертация (lat, lon) → (x, y) в координатах итогового кадра (1920x1080)."""
    px, py = lat_lon_to_pixel(lat, lon, zoom)
    frame_x = int(px - grid["tile_x_start"] * TILE_SIZE - grid["offset_x"])
    frame_y = int(py - grid["tile_y_start"] * TILE_SIZE - grid["offset_y"])
    return frame_x, frame_y
