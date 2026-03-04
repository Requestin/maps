import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# === Яндекс Tiles API ===
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "")
YANDEX_TILE_URL = os.getenv(
    "YANDEX_TILE_URL",
    "https://core-renderer-tiles.maps.yandex.net/tiles"
    "?l=map&x={x}&y={y}&z={z}&scale=1&lang=ru_RU&theme=dark&apikey={apikey}",
)
TILE_SIZE = 256
TILE_DOWNLOAD_TIMEOUT = 10
TILE_MAX_RETRIES = 3
TILE_RETRY_DELAY = 1.0

# === Видео ===
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30
VIDEO_DURATION = 10
VIDEO_CODEC = "libx264"
VIDEO_PRESET = "fast"
VIDEO_CRF = 23

# === Геокодирование (Яндекс HTTP Геокодер) ===
YANDEX_GEOCODER_API_KEY = os.getenv("YANDEX_GEOCODER_API_KEY", "")
YANDEX_GEOCODER_URL = "https://geocode-maps.yandex.ru/v1/"
YANDEX_GEOCODER_TIMEOUT = 10

# === Карта ===
SINGLE_CITY_RADIUS_KM = 150
TWO_CITY_PADDING_RATIO = 0.20
DARK_THEME_FALLBACK = True

# === Анимация: маркеры ===
PULSE_FREQUENCY = 1.0
MARKER_BASE_RADIUS = 15
MARKER_PULSE_AMPLITUDE = 8
MARKER_COLOR_BGR = (0, 0, 255)
MARKER_ALPHA_MIN = 0.4
MARKER_ALPHA_MAX = 1.0

# === Анимация: пунктирная линия ===
DASH_LENGTH = 20
DASH_GAP = 15
DASH_SPEED = 35.0
LINE_COLOR_BGR = (0, 0, 255)
LINE_THICKNESS = 3

# === Анимация: «дыхание» камеры ===
CAMERA_BREATH_ENABLED = True
CAMERA_BREATH_CYCLES = 2       # количество zoom-циклов за VIDEO_DURATION
CAMERA_BREATH_AMPLITUDE = 0.04  # макс. относительное увеличение масштаба (~3%)

# === Подписи городов ===
if sys.platform == "win32":
    _default_font = r"C:\Windows\Fonts\arial.ttf"
else:
    _default_font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

LABEL_FONT_PATH = os.getenv("LABEL_FONT_PATH", _default_font)
LABEL_FONT_SIZE = 28
LABEL_COLOR_RGB = (255, 0, 0)
LABEL_OUTLINE_COLOR_RGB = (255, 255, 255)
LABEL_OUTLINE_WIDTH = 2
LABEL_OFFSET_X = 20
LABEL_OFFSET_Y = -10

# === Атрибуция Яндекса ===
ATTRIBUTION_TEXT = "\u00a9 \u042f\u043d\u0434\u0435\u043a\u0441"
ATTRIBUTION_FONT_SIZE = 16
ATTRIBUTION_COLOR_RGB = (180, 180, 180)
ATTRIBUTION_MARGIN = 10

# === Очередь задач ===
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
MAX_QUEUE_SIZE = 10
CELERY_TASK_CONCURRENCY = 1

# === Хранение ===
VIDEO_OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", str(BASE_DIR / "videos")))
VIDEO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_TTL_DAYS = 7
CLEANUP_INTERVAL_SECONDS = 3600

# === Логирование ===
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG")
LOG_DIR = Path(os.getenv("LOG_DIR", str(BASE_DIR / "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_ROTATION = "100 MB"
LOG_RETENTION = "30 days"
LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} | {message}"

# === FFmpeg ===
FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")
