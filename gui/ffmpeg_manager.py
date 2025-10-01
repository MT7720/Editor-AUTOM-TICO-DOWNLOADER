"""Utilities related to FFmpeg discovery and inspection."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from typing import List, Optional

from .utils import logger


class FFmpegManager:
    """Locate FFmpeg executables and inspect available encoders."""

    @staticmethod
    def find_executable() -> Optional[str]:
        executable = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
        logger.info("Procurando FFmpeg executável: %s", executable)

        found_path = shutil.which(executable)
        if found_path:
            logger.info("FFmpeg encontrado via PATH: %s", found_path)
            return found_path

        candidate_paths: List[str] = []

        def add_candidate(path: Optional[str]) -> None:
            if not path:
                return
            normalized = os.path.normpath(path)
            if normalized not in candidate_paths:
                candidate_paths.append(normalized)

        system_name = platform.system()

        if system_name == "Windows":
            program_files = os.environ.get("ProgramFiles") or r"C:\\Program Files"
            program_files_x86 = os.environ.get("ProgramFiles(x86)") or r"C:\\Program Files (x86)"
            local_app_data = os.environ.get("LOCALAPPDATA")

            add_candidate(os.path.join(program_files, "ffmpeg", "bin", executable))
            add_candidate(os.path.join(program_files_x86, "ffmpeg", "bin", executable))
            if local_app_data:
                add_candidate(os.path.join(local_app_data, "Programs", "ffmpeg", "bin", executable))
            add_candidate(os.path.join("C:\\FFmpeg", "bin", executable))

        app_directories = []
        frozen_dir = getattr(sys, "_MEIPASS", None)
        if frozen_dir:
            app_directories.append(frozen_dir)
        executable_dir = os.path.dirname(getattr(sys, "executable", "") or "")
        if executable_dir:
            app_directories.append(executable_dir)

        for directory in app_directories:
            add_candidate(os.path.join(directory, executable))
            add_candidate(os.path.join(directory, "ffmpeg", "bin", executable))

        for path in candidate_paths:
            logger.info("Verificando FFmpeg em: %s", path)
            if os.path.exists(path):
                logger.info("FFmpeg encontrado em: %s", path)
                return path

        logger.info("FFmpeg não encontrado nos caminhos verificados")
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
