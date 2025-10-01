"""Shared constants for the GUI application."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

try:
    import video_processing_logic  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    video_processing_logic = None

from .utils import get_app_data_path, resource_path

APP_NAME = "Editor & Downloader Automático"
DEFAULT_GEOMETRY = "1200x900"
CONFIG_FILE = "video_editor_config.json"
ICON_FILE = resource_path("icone.ico")

SUPPORTED_NARRATION_FT = [
    ("Arquivos de Áudio", "*.mp3 *.wav *.aac *.ogg *.flac"),
    ("Todos os arquivos", "*.*"),
]
SUPPORTED_MUSIC_FT = SUPPORTED_NARRATION_FT
SUPPORTED_SUBTITLE_FT = [
    ("Arquivos de Legenda SRT", "*.srt"),
    ("Todos os arquivos", "*.*"),
]
SUPPORTED_VIDEO_FT = [
    ("Arquivos de Vídeo", "*.mp4 *.mov *.avi *.mkv"),
    ("Todos os arquivos", "*.*"),
]
SUPPORTED_PRESENTER_FT = [
    ("Vídeos de Apresentador", "*.mov *.mp4 *.mkv"),
    ("Todos os arquivos", "*.*"),
]
SUPPORTED_IMAGE_FT = [
    ("Arquivos de Imagem", "*.jpg *.jpeg *.png *.bmp *.webp"),
    ("Todos os arquivos", "*.*"),
]
SUPPORTED_PNG_FT = [("Arquivo PNG", "*.png"), ("Todos os arquivos", "*.*")]
SUPPORTED_FONT_FT = [("Arquivos de Fonte", "*.ttf *.otf"), ("Todos os arquivos", "*.*")]

RESOLUTIONS = [
    "1080p (1920x1080)",
    "720p (1280x720)",
    "Vertical (1080x1920)",
    "480p (854x480)",
]
SUBTITLE_POSITIONS = {
    "Inferior Central": 2,
    "Inferior Esquerda": 1,
    "Inferior Direita": 3,
    "Meio Central": 5,
    "Meio Esquerda": 4,
    "Meio Direita": 6,
    "Superior Central": 8,
    "Superior Esquerda": 7,
    "Superior Direita": 9,
}
OVERLAY_POSITIONS = [
    "Superior Esquerdo",
    "Superior Direito",
    "Inferior Esquerdo",
    "Inferior Direito",
]
PRESENTER_POSITIONS = [
    "Inferior Esquerdo",
    "Inferior Central",
    "Inferior Direito",
]

SLIDESHOW_TRANSITIONS = {
    "Nenhuma": "none",
    "Esmaecer (Fade)": "fade",
    "Limpar para Esquerda": "wipeleft",
    "Limpar para Direita": "wiperight",
    "Limpar para Cima": "wipeup",
    "Limpar para Baixo": "wipedown",
    "Deslizar para Esquerda": "slideleft",
    "Deslizar para Direita": "slideright",
    "Deslizar para Cima": "slideup",
    "Deslizar para Baixo": "slidedown",
    "Círculo (Radial)": "radial",
    "Corte Circular": "circlecrop",
    "Diagonal (Sup-Esq)": "diagtl",
    "Fatiar Horizontal": "hrslice",
    "Fatiar Vertical": "vuslice",
}
SLIDESHOW_MOTIONS = ["Nenhum", "Zoom In", "Zoom Out", "Pan Esquerda", "Pan Direita"]
EFFECT_BLEND_MODES = {
    "Tela (Screen)": "screen",
    "Sobrepor (Overlay)": "overlay",
    "Luz Suave (Softlight)": "softlight",
    "Luz Direta (Hardlight)": "hardlight",
    "Clarear (Lighten)": "lighten",
    "Escurecer (Darken)": "darken",
    "Diferença (Difference)": "difference",
    "Multiplicar (Multiply)": "multiply",
}

if video_processing_logic and hasattr(video_processing_logic, "LANGUAGE_CODE_MAP"):
    LANGUAGE_CODE_MAP: Dict[str, str] = video_processing_logic.LANGUAGE_CODE_MAP  # type: ignore[assignment]
else:
    LANGUAGE_CODE_MAP = {
        "PT": "Português",
        "ING": "Inglês",
        "ESP": "Espanhol",
        "FRAN": "Francês",
        "BUL": "Búlgaro",
        "ROM": "Romeno",
        "ALE": "Alemão",
        "GREGO": "Grego",
        "ITA": "Italiano",
        "POL": "Polonês",
        "HOLAND": "Holandês",
    }

APP_DATA_PATH = get_app_data_path()

__all__ = [
    "APP_NAME",
    "DEFAULT_GEOMETRY",
    "CONFIG_FILE",
    "ICON_FILE",
    "SUPPORTED_NARRATION_FT",
    "SUPPORTED_MUSIC_FT",
    "SUPPORTED_SUBTITLE_FT",
    "SUPPORTED_VIDEO_FT",
    "SUPPORTED_PRESENTER_FT",
    "SUPPORTED_IMAGE_FT",
    "SUPPORTED_PNG_FT",
    "SUPPORTED_FONT_FT",
    "RESOLUTIONS",
    "SUBTITLE_POSITIONS",
    "OVERLAY_POSITIONS",
    "PRESENTER_POSITIONS",
    "SLIDESHOW_TRANSITIONS",
    "SLIDESHOW_MOTIONS",
    "EFFECT_BLEND_MODES",
    "LANGUAGE_CODE_MAP",
    "APP_DATA_PATH",
]
