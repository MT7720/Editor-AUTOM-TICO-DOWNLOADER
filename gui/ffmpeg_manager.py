"""Utilities related to FFmpeg discovery and inspection."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import List, Optional

from .utils import logger


class FFmpegManager:
    """Locate FFmpeg executables and inspect available encoders."""

    @staticmethod
    def find_executable() -> Optional[str]:
        executable = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
        found_path = shutil.which(executable)
        if found_path:
            return found_path
        if platform.system() == "Windows":
            search_dirs = [
                os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "ffmpeg", "bin"),
                "C:\\FFmpeg\\bin",
            ]
            for directory in search_dirs:
                potential_path = os.path.join(directory, "ffmpeg.exe")
                if os.path.exists(potential_path):
                    return potential_path
        return None

    @staticmethod
    def check_encoders(ffmpeg_path: str) -> List[str]:
        encoders_found = ["libx264"]
        if not ffmpeg_path or not os.path.isfile(ffmpeg_path):
            return encoders_found
        try:
            creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            result = subprocess.run(
                [ffmpeg_path, "-encoders"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
                creationflags=creation_flags,
                encoding="utf-8",
                errors="ignore",
            )
            if "h264_nvenc" in result.stdout:
                encoders_found.append("h264_nvenc")
            if "hevc_nvenc" in result.stdout:
                encoders_found.append("hevc_nvenc")
            logger.info("Encoders FFmpeg detetados: %s", encoders_found)
        except Exception as exc:  # pragma: no cover - defensive subprocess handling
            logger.warning("Falha ao verificar os encoders do FFmpeg: %s", exc)
        return encoders_found


__all__ = ["FFmpegManager"]
