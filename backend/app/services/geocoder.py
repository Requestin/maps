"""Геокодирование: название города → координаты (lat, lon) через Яндекс HTTP Геокодер."""

import time

import requests
from loguru import logger

from backend.app.config import (
    YANDEX_GEOCODER_API_KEY,
    YANDEX_GEOCODER_TIMEOUT,
    YANDEX_GEOCODER_URL,
)


def geocode_city(city_name: str) -> tuple[float, float]:
    """Геокодирование названия города в координаты через Яндекс Геокодер.

    Args:
        city_name: название города (например, "Москва").

    Returns:
        (latitude, longitude).

    Raises:
        ValueError: если город не найден или произошла ошибка.
    """
    logger.info("geocode_city: запрос геокодирования для '{}'", city_name)
    start = time.perf_counter()

    if not YANDEX_GEOCODER_API_KEY:
        raise ValueError("YANDEX_GEOCODER_API_KEY не задан в .env")

    params = {
        "apikey": YANDEX_GEOCODER_API_KEY,
        "geocode": city_name,
        "format": "json",
        "results": 1,
        "lang": "ru_RU",
    }

    try:
        resp = requests.get(
            YANDEX_GEOCODER_URL,
            params=params,
            timeout=YANDEX_GEOCODER_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        elapsed = time.perf_counter() - start
        logger.error("geocode_city: таймаут ({:.2f}с) для '{}'", elapsed, city_name)
        raise ValueError(f"Таймаут геокодирования для '{city_name}'")
    except requests.exceptions.RequestException as exc:
        elapsed = time.perf_counter() - start
        logger.error("geocode_city: ошибка сети ({:.2f}с) для '{}': {}", elapsed, city_name, exc)
        raise ValueError(f"Ошибка сети при геокодировании '{city_name}': {exc}")

    elapsed = time.perf_counter() - start

    if resp.status_code == 403:
        logger.error("geocode_city: невалидный API-ключ (HTTP 403)")
        raise ValueError("Невалидный YANDEX_GEOCODER_API_KEY")

    if resp.status_code != 200:
        logger.error(
            "geocode_city: HTTP {} для '{}' ({:.2f}с): {}",
            resp.status_code, city_name, elapsed, resp.text[:200],
        )
        raise ValueError(f"Яндекс Геокодер вернул HTTP {resp.status_code} для '{city_name}'")

    data = resp.json()

    members = (
        data.get("response", {})
        .get("GeoObjectCollection", {})
        .get("featureMember", [])
    )

    if not members:
        logger.warning("geocode_city: город '{}' не найден ({:.2f}с)", city_name, elapsed)
        raise ValueError(f"Город '{city_name}' не найден")

    geo_obj = members[0]["GeoObject"]
    pos = geo_obj["Point"]["pos"]
    lon_str, lat_str = pos.split()
    lon = float(lon_str)
    lat = float(lat_str)

    name = geo_obj.get("name", "")
    description = geo_obj.get("description", "")

    logger.info(
        "geocode_city: '{}' -> lat={}, lon={} (name='{}', desc='{}', {:.2f}с)",
        city_name, lat, lon, name, description, elapsed,
    )
    return lat, lon
