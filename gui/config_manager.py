"""Configuration management helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

from .constants import (
    CONFIG_FILE,
    EFFECT_BLEND_MODES,
    OVERLAY_POSITIONS,
    PRESENTER_POSITIONS,
    RESOLUTIONS,
    SLIDESHOW_MOTIONS,
    SLIDESHOW_TRANSITIONS,
    SUBTITLE_POSITIONS,
    INTRO_FONT_CHOICES,
)
from .utils import logger


LICENSE_CONFIG_KEYS = {
    "license_credentials_path",
    "license_api_token",
    "license_api_url",
}


def _migrate_legacy_license_fields(config: Dict[str, Any]) -> None:
    """Atualiza chaves antigas do Keygen para o novo formato de serviço."""

    config.pop("license_account_id", None)
    product_token = config.pop("license_product_token", None)
    api_base_url = config.pop("license_api_base_url", None)

    if isinstance(product_token, str) and isinstance(api_base_url, str):
        config.setdefault("license_api_token", product_token)
        config.setdefault("license_api_url", api_base_url)



class ConfigManager:
    """Persist and restore application configuration."""

    @staticmethod
    def load_config() -> Dict[str, Any]:
        default_config: Dict[str, Any] = {
            "ffmpeg_path": "",
            "output_folder": str(Path.home() / "Videos"),
            "last_download_folder": str(Path.home() / "Downloads"),
            "last_video_folder": "",
            "last_audio_folder": "",
            "last_image_folder": "",
            "last_srt_folder": "",
            "last_root_folder": "",
            "last_png_folder": "",
            "last_mixed_folder": "",
            "last_effect_folder": "",
            "last_presenter_folder": "",
            "video_codec": "Automático",
            "resolution": RESOLUTIONS[0],
            "narration_volume": 0,
            "music_volume": -15,
            "subtitle_fontsize": 48,
            "subtitle_textcolor": "#FFFFFF",
            "subtitle_outlinecolor": "#000000",
            "subtitle_position": list(SUBTITLE_POSITIONS.keys())[0],
            "subtitle_bold": True,
            "subtitle_italic": False,
            "subtitle_font_file": "",
            "image_duration": 5,
            "slideshow_transition": list(SLIDESHOW_TRANSITIONS.keys())[1],
            "slideshow_transition_duration": 1.0,
            "slideshow_motion": SLIDESHOW_MOTIONS[1],
            "png_overlay_path": "",
            "png_overlay_position": OVERLAY_POSITIONS[3],
            "png_overlay_scale": 0.15,
            "png_overlay_opacity": 1.0,
            "batch_music_behavior": "loop",
            "add_fade_out": False,
            "fade_out_duration": 10,
            "effect_overlay_path": "",
            "effect_blend_mode": list(EFFECT_BLEND_MODES.keys())[0],
            "presenter_video_path": "",
            "presenter_position": PRESENTER_POSITIONS[1],
            "presenter_scale": 0.40,
            "presenter_chroma_enabled": False,
            "presenter_chroma_color": "#00FF00",
            "presenter_chroma_similarity": 0.2,
            "presenter_chroma_blend": 0.1,
            "show_tech_logs": False,
            "intro_enabled": False,
            "intro_default_text": "",
            "intro_texts": {},
            "intro_language_code": "auto",
            "intro_font_choice": INTRO_FONT_CHOICES[0] if INTRO_FONT_CHOICES else "Automático",
            "intro_font_bold": False,
            "intro_typing_duration_seconds": 10,
            "intro_hold_duration_seconds": 2,
            "single_language_code": "auto",
            "banner_enabled": False,
            "banner_default_text": "",
            "banner_texts": {},
            "banner_language_code": "auto",
            "banner_use_gradient": False,
            "banner_solid_color": "#FFB347",
            "banner_gradient_start": "#FF512F",
            "banner_gradient_end": "#DD2476",
            "banner_font_color": "#FFFFFF",
            "banner_duration": 5.0,
            "banner_height_ratio": 0.18,
            "banner_font_scale": 0.45,
            "banner_outline_enabled": False,
            "banner_outline_color": "#000000",
            "banner_outline_offset": 2.0,
            "banner_shadow_enabled": False,
            "banner_shadow_color": "#000000",
            "banner_shadow_offset_x": 3.0,
            "banner_shadow_offset_y": 3.0,
        }
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    file_content = f.read()
                    if file_content:
                        saved_config = json.loads(file_content)
                        for key in list(saved_config.keys()):
                            if key.startswith("banner_preview_language"):
                                saved_config.pop(key, None)
                        _migrate_legacy_license_fields(saved_config)
                        default_config.update(saved_config)
        except Exception as exc:  # pragma: no cover - defensive I/O
            logger.warning("Não foi possível carregar o ficheiro de configuração: %s", exc)
        return default_config

    @staticmethod
    def save_config(config: Dict[str, Any]) -> None:
        try:
            preserved_values: Dict[str, Any] = {}

            if os.path.exists(CONFIG_FILE):
                try:
                    with open(CONFIG_FILE, "r", encoding="utf-8") as existing_file:
                        file_content = existing_file.read()
                    if file_content:
                        previous_config = json.loads(file_content)
                        preserved_values = {
                            key: value
                            for key, value in previous_config.items()
                            if key in LICENSE_CONFIG_KEYS
                        }
                except (OSError, ValueError) as exc:
                    logger.warning(
                        "Não foi possível ler o ficheiro de configuração existente: %s",
                        exc,
                    )

            config_to_write = dict(config)
            for key, value in preserved_values.items():
                config_to_write.setdefault(key, value)

            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config_to_write, f, indent=2, ensure_ascii=False)
        except Exception as exc:  # pragma: no cover - defensive I/O
            logger.error("Erro ao guardar o ficheiro de configuração: %s", exc)


__all__ = ["ConfigManager"]
