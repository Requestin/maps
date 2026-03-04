"""FFmpeg pipe encoding: кадры (numpy BGR) → MP4 файл."""

import subprocess
import time
from pathlib import Path

import numpy as np
from loguru import logger

from backend.app.config import (
    FFMPEG_BIN,
    VIDEO_CRF,
    VIDEO_FPS,
    VIDEO_HEIGHT,
    VIDEO_PRESET,
    VIDEO_WIDTH,
)


class VideoEncoder:
    """Потоковый кодировщик: принимает numpy-кадры, пишет MP4 через stdin FFmpeg."""

    def __init__(self, output_path: str | Path):
        self.output_path = str(output_path)
        self._process: subprocess.Popen | None = None
        self._frame_count = 0
        self._start_time = 0.0

    def start(self) -> None:
        """Запустить процесс FFmpeg."""
        cmd = [
            FFMPEG_BIN,
            "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}",
            "-r", str(VIDEO_FPS),
            "-i", "pipe:0",
            "-c:v", "libx264",
            "-preset", VIDEO_PRESET,
            "-crf", str(VIDEO_CRF),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            self.output_path,
        ]
        logger.info("FFmpeg запуск: {}", " ".join(cmd))
        self._start_time = time.perf_counter()

        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        logger.debug("FFmpeg процесс запущен, PID={}", self._process.pid)

    def write_frame(self, frame: np.ndarray) -> None:
        """Записать один BGR-кадр (numpy array shape HxWx3, dtype uint8)."""
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("VideoEncoder не запущен; вызовите start() сначала")

        raw = frame.tobytes()
        self._process.stdin.write(raw)
        self._frame_count += 1

    def finish(self) -> dict:
        """Закрыть stdin, дождаться завершения FFmpeg.

        Returns:
            {"return_code": int, "stderr": str, "frames": int, "elapsed_sec": float}.
        """
        if self._process is None:
            raise RuntimeError("VideoEncoder не запущен")

        self._process.stdin.close()
        _, stderr_bytes = self._process.communicate()
        elapsed = time.perf_counter() - self._start_time

        stderr_text = stderr_bytes.decode("utf-8", errors="replace")
        return_code = self._process.returncode

        file_size = 0
        try:
            file_size = Path(self.output_path).stat().st_size
        except OSError:
            pass

        logger.info(
            "FFmpeg завершён: return_code={}, кадров={}, время={:.2f}с, файл={} ({} байт)",
            return_code, self._frame_count, elapsed, self.output_path, file_size,
        )
        if return_code != 0:
            logger.error("FFmpeg stderr:\n{}", stderr_text)
        else:
            logger.debug("FFmpeg stderr (последние 500 символов): ...{}", stderr_text[-500:])

        self._process = None

        return {
            "return_code": return_code,
            "stderr": stderr_text,
            "frames": self._frame_count,
            "elapsed_sec": elapsed,
            "file_size": file_size,
        }
