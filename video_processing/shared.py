"""Shared imports and helpers used by the video processing pipeline."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, IO, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFile, ImageFont

from processing.ffmpeg_pipeline import (
    escape_ffmpeg_path,
    execute_ffmpeg,
    get_codec_params,
    probe_media_properties,
)
from processing.language_utils import (
    LANGUAGE_ALIASES,
    LANGUAGE_CODE_MAP,
    LANGUAGE_TRANSLATION_CODES,
    attempt_translate_text,
    infer_language_code_from_filename,
    infer_language_code_from_name,
    normalize_language_code,
)
from processing.typing_renderer import create_typing_intro_clip, wrap_text_to_width

LOGGER_NAME = "video_processing_logic"
logger = logging.getLogger(LOGGER_NAME)

# Permit loading truncated images exactly as the legacy module did.
ImageFile.LOAD_TRUNCATED_IMAGES = True

# Backwards-compatible aliases -------------------------------------------------
_normalize_language_code = normalize_language_code
_infer_language_code_from_name = infer_language_code_from_name
_infer_language_code_from_filename = infer_language_code_from_filename
_attempt_translate_text = attempt_translate_text
_wrap_text_to_width = wrap_text_to_width
_create_typing_intro_clip = create_typing_intro_clip
_execute_ffmpeg = execute_ffmpeg
_escape_ffmpeg_path = escape_ffmpeg_path
_probe_media_properties = probe_media_properties
_get_codec_params = get_codec_params

__all__ = [
    "LOGGER_NAME",
    "logger",
    "Image",
    "ImageDraw",
    "ImageFile",
    "ImageFont",
    "LANGUAGE_ALIASES",
    "LANGUAGE_CODE_MAP",
    "LANGUAGE_TRANSLATION_CODES",
    "_normalize_language_code",
    "_infer_language_code_from_name",
    "_infer_language_code_from_filename",
    "_attempt_translate_text",
    "_wrap_text_to_width",
    "_create_typing_intro_clip",
    "_execute_ffmpeg",
    "_escape_ffmpeg_path",
    "_probe_media_properties",
    "_get_codec_params",
]
