# MapVideo — генерация анимированных карт в MP4

Веб-сервис для генерации коротких анимированных MP4-видео с картой (один город или маршрут между двумя городами) на основе тайлов Яндекс Карт.

Полное техническое описание: [SPECIFICATION.md](SPECIFICATION.md).

## Установка и запуск на Windows (без Docker)

### 1. Предварительные зависимости

- Python 3.12+ — скачать с python.org, при установке отметить галочку Add to PATH.
- FFmpeg — скачать с gyan.dev/ffmpeg/builds (release full), распаковать, добавить папку bin в PATH.
- Redis: для Windows рекомендуется Memurai (memurai.com), либо внешний Redis на Linux-сервере.
- Git — любая актуальная версия.

### 2. Клонирование и виртуальное окружение

    git clone <URL_REPO> maps
    cd maps
    python -m venv .venv
    .venv\Scripts\activate
    pip install -r backend\requirements.txt

### 3. Настройка .env

Скопируйте шаблон:

    copy .env.example .env

Отредактируйте .env и укажите свои ключи:

    YANDEX_API_KEY=<ключ для тайлов>              # JavaScript API
    YANDEX_GEOCODER_API_KEY=<ключ геокодера>     # JavaScript API и HTTP Геокодер
    REDIS_URL=redis://localhost:6379/0
    VIDEO_OUTPUT_DIR=videos
    LOG_DIR=logs

Ключи получаются в кабинете разработчика Яндекса. Для тайлов и геокодера используются разные сервисы, поэтому ключи могут отличаться.

### 4. Запуск

Нужны 3 процесса (каждый в отдельном терминале):

1. Redis — если установлен Memurai, убедитесь, что служба запущена.

2. FastAPI (backend):

       .venv\Scripts\activate
       uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload

3. Celery worker:

       .venv\Scripts\activate
       celery -A backend.app.celery_app worker --loglevel=debug --pool=solo

4. (Опционально) Celery beat:

       .venv\Scripts\activate
       celery -A backend.app.celery_app beat --loglevel=info

Также можно использовать скрипт run_all.bat для автоматического запуска под Windows.

### 5. Веб-интерфейс

Откройте в браузере: http://127.0.0.1:8000

## Запуск на Ubuntu-сервере

    sudo apt update
    sudo apt install -y python3 python3-venv python3-pip ffmpeg redis-server git

    git clone <URL_REPO> maps && cd maps
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r backend/requirements.txt

    cp .env.example .env
    # отредактируйте .env

    sudo systemctl enable --now redis-server

    uvicorn backend.app.main:app --host 0.0.0.0 --port 5555
    celery -A backend.app.celery_app worker --loglevel=debug --concurrency=1
    celery -A backend.app.celery_app beat --loglevel=info

Для удобства в репозитории есть готовые systemd-файлы:

- mapvideo-uvicorn.service (порт 5555)
- mapvideo-celery-worker.service
- mapvideo-celery-beat.service
- mapvideo.target (управляет всем стеком)

## Структура проекта

    maps/
      backend/
        app/
          main.py            # FastAPI
          config.py          # Конфигурация
          celery_app.py      # Celery
          api/routes.py      # HTTP-эндпоинты
          services/          # Геокодер, тайлы, рендеринг, FFmpeg
          tasks/             # Celery-задачи
          models/schemas.py  # Pydantic-схемы
        requirements.txt
      frontend/              # HTML/CSS/JS
      videos/                # Сгенерированные видео (gitignored)
      logs/                  # Логи (gitignored)
      .env.example
      SPECIFICATION.md
