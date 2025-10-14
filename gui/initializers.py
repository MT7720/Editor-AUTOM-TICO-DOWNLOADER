"""Helper routines to prepare application state."""

from __future__ import annotations

import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

import ttkbootstrap as ttk

from .constants import (
    EFFECT_BLEND_MODES,
    LANGUAGE_CODE_MAP,
    OVERLAY_POSITIONS,
    PRESENTER_POSITIONS,
    RESOLUTIONS,
    SLIDESHOW_MOTIONS,
    SLIDESHOW_TRANSITIONS,
    SUBTITLE_POSITIONS,
    INTRO_FONT_CHOICES,
)


def initialize_variables(app: Any, config: Dict[str, Any]) -> None:
    app.ffmpeg_path_var = ttk.StringVar(value=config.get("ffmpeg_path", ""))
    app.media_path_single = ttk.StringVar(value="")
    app.narration_file_single = ttk.StringVar()
    app.subtitle_file_single = ttk.StringVar()
    app.batch_video_parent_folder = ttk.StringVar()
    app.batch_image_parent_folder = ttk.StringVar(value=config.get("last_image_folder", ""))
    app.batch_mixed_media_folder = ttk.StringVar(value=config.get("last_mixed_folder", ""))
    app.batch_audio_folder = ttk.StringVar()
    app.batch_srt_folder = ttk.StringVar()
    app.batch_root_folder = ttk.StringVar(value=config.get("last_root_folder", ""))
    app.music_file_single = ttk.StringVar()
    app.music_folder_path = ttk.StringVar()
    app.output_folder = ttk.StringVar(value=config.get("output_folder", str(Path.home() / "Videos")))
    app.output_filename_single = ttk.StringVar(value="video_final.mp4")
    app.subtitle_font_file = ttk.StringVar(value=config.get("subtitle_font_file", ""))
    app.media_type = ttk.StringVar(value="video_single")
    app.resolution_var = ttk.StringVar(value=config.get("resolution", RESOLUTIONS[0]))
    app.video_codec_var = ttk.StringVar(value=config.get("video_codec", "Automático"))
    app.image_duration_var = ttk.IntVar(value=config.get("image_duration", 5))
    app.transition_name_var = ttk.StringVar(
        value=config.get("slideshow_transition", list(SLIDESHOW_TRANSITIONS.keys())[1])
    )
    app.transition_duration_var = ttk.DoubleVar(value=config.get("slideshow_transition_duration", 1.0))
    app.motion_var = ttk.StringVar(value=config.get("slideshow_motion", SLIDESHOW_MOTIONS[1]))
    app.narration_volume_var = ttk.DoubleVar(value=config.get("narration_volume", 0))
    app.music_volume_var = ttk.DoubleVar(value=config.get("music_volume", -15))
    app.subtitle_fontsize_var = ttk.IntVar(value=config.get("subtitle_fontsize", 48))
    app.subtitle_textcolor_var = ttk.StringVar(value=config.get("subtitle_textcolor", "#FFFFFF"))
    app.subtitle_outlinecolor_var = ttk.StringVar(value=config.get("subtitle_outlinecolor", "#000000"))
    app.subtitle_position_var = ttk.StringVar(
        value=config.get("subtitle_position", list(SUBTITLE_POSITIONS.keys())[0])
    )
    app.subtitle_bold_var = ttk.BooleanVar(value=config.get("subtitle_bold", True))
    app.subtitle_italic_var = ttk.BooleanVar(value=config.get("subtitle_italic", False))
    app.png_overlay_path_var = ttk.StringVar(value=config.get("png_overlay_path", ""))
    app.png_overlay_position_var = ttk.StringVar(value=config.get("png_overlay_position", OVERLAY_POSITIONS[3]))
    app.png_overlay_scale_var = ttk.DoubleVar(value=config.get("png_overlay_scale", 0.15))
    app.png_overlay_opacity_var = ttk.DoubleVar(value=config.get("png_overlay_opacity", 1.0))
    app.batch_music_behavior_var = ttk.StringVar(value=config.get("batch_music_behavior", "loop"))
    app.add_fade_out_var = ttk.BooleanVar(value=config.get("add_fade_out", False))
    app.fade_out_duration_var = ttk.IntVar(value=config.get("fade_out_duration", 10))
    app.effect_overlay_path_var = ttk.StringVar(value=config.get("effect_overlay_path", ""))
    app.effect_blend_mode_var = ttk.StringVar(value=config.get("effect_blend_mode", list(EFFECT_BLEND_MODES.keys())[0]))
    app.presenter_video_path_var = ttk.StringVar(value=config.get("presenter_video_path", ""))
    app.presenter_position_var = ttk.StringVar(value=config.get("presenter_position", PRESENTER_POSITIONS[1]))
    app.presenter_scale_var = ttk.DoubleVar(value=config.get("presenter_scale", 0.40))
    app.presenter_chroma_enabled_var = ttk.BooleanVar(value=config.get("presenter_chroma_enabled", False))
    app.presenter_chroma_color_var = ttk.StringVar(value=config.get("presenter_chroma_color", "#00FF00"))
    app.presenter_chroma_similarity_var = ttk.DoubleVar(value=config.get("presenter_chroma_similarity", 0.2))
    app.presenter_chroma_blend_var = ttk.DoubleVar(value=config.get("presenter_chroma_blend", 0.1))
    app.show_tech_logs_var = ttk.BooleanVar(value=config.get("show_tech_logs", False))
    app.download_output_path_var = ttk.StringVar(
        value=config.get("last_download_folder", str(Path.home() / "Downloads"))
    )
    app.download_format_var = ttk.StringVar(value="MP4")
    app.download_playlist_var = ttk.BooleanVar(value=config.get("download_playlist_enabled", False))
    playlist_limit = config.get("download_playlist_limit", "Todos") or "Todos"
    app.playlist_items_limit_var = ttk.StringVar(value=str(playlist_limit))

    app.intro_enabled_var = ttk.BooleanVar(value=config.get("intro_enabled", False))
    app.intro_default_text_var = ttk.StringVar(value=config.get("intro_default_text", ""))
    app.intro_language_var = ttk.StringVar(value=config.get("intro_language_code", "auto"))
    default_intro_font = config.get("intro_font_choice") or (INTRO_FONT_CHOICES[0] if INTRO_FONT_CHOICES else "Automático")
    app.intro_font_choice_var = ttk.StringVar(value=default_intro_font)
    app.intro_font_bold_var = ttk.BooleanVar(value=config.get("intro_font_bold", False))
    typing_duration = config.get("intro_typing_duration_seconds", 10)
    try:
        typing_duration = int(typing_duration)
    except (TypeError, ValueError):
        typing_duration = 10
    if typing_duration not in {10, 15, 20, 30}:
        typing_duration = 10
    hold_duration = config.get("intro_hold_duration_seconds", 2)
    try:
        hold_duration = int(hold_duration)
    except (TypeError, ValueError):
        hold_duration = 2
    if hold_duration <= 0:
        hold_duration = 2
    app.intro_typing_duration_seconds_var = ttk.IntVar(value=typing_duration)
    app.intro_hold_duration_seconds_var = ttk.IntVar(value=hold_duration)

    app.banner_enabled_var = ttk.BooleanVar(value=config.get("banner_enabled", False))
    app.banner_default_text_var = ttk.StringVar(value=config.get("banner_default_text", ""))
    app.banner_language_code_var = ttk.StringVar(value=config.get("banner_language_code", "auto"))
    app.banner_use_gradient_var = ttk.BooleanVar(value=config.get("banner_use_gradient", False))
    app.banner_solid_color_var = ttk.StringVar(value=config.get("banner_solid_color", "#FFB347"))
    app.banner_gradient_start_var = ttk.StringVar(value=config.get("banner_gradient_start", "#FF512F"))
    app.banner_gradient_end_var = ttk.StringVar(value=config.get("banner_gradient_end", "#DD2476"))
    app.banner_font_color_var = ttk.StringVar(value=config.get("banner_font_color", "#FFFFFF"))
    app.banner_duration_var = ttk.DoubleVar(value=config.get("banner_duration", 5.0))
    app.banner_height_ratio_var = ttk.DoubleVar(value=config.get("banner_height_ratio", 0.18))
    app.banner_font_scale_var = ttk.DoubleVar(value=config.get("banner_font_scale", 0.45))
    app.banner_texts = dict(config.get("banner_texts") or {})
    app.banner_outline_enabled_var = ttk.BooleanVar(value=config.get("banner_outline_enabled", False))
    app.banner_outline_color_var = ttk.StringVar(value=config.get("banner_outline_color", "#000000"))
    app.banner_outline_offset_var = ttk.DoubleVar(value=config.get("banner_outline_offset", 2.0))
    app.banner_shadow_enabled_var = ttk.BooleanVar(value=config.get("banner_shadow_enabled", False))
    app.banner_shadow_color_var = ttk.StringVar(value=config.get("banner_shadow_color", "#000000"))
    app.banner_shadow_offset_x_var = ttk.DoubleVar(value=config.get("banner_shadow_offset_x", 3.0))
    app.banner_shadow_offset_y_var = ttk.DoubleVar(value=config.get("banner_shadow_offset_y", 3.0))

    stored_language_code = config.get("single_language_code", "auto") or "auto"
    if isinstance(stored_language_code, str) and stored_language_code.lower() != "auto":
        stored_language_code = stored_language_code.upper()
    else:
        stored_language_code = "auto"

    app.language_code_to_display = {"auto": "Automático (detectar)"}
    for code, name in LANGUAGE_CODE_MAP.items():
        app.language_code_to_display[code] = f"{name} ({code})"
    app.language_display_to_code = {display: code for code, display in app.language_code_to_display.items()}

    app.single_language_code_var = ttk.StringVar(value=stored_language_code)
    default_display = app.language_code_to_display.get(stored_language_code, app.language_code_to_display["auto"])
    app.single_language_display_var = ttk.StringVar(value=default_display)

    app.path_vars = {
        "narration_single": app.narration_file_single,
        "subtitle_single": app.subtitle_file_single,
        "media_single": app.media_path_single,
        "batch_video": app.batch_video_parent_folder,
        "batch_image": app.batch_image_parent_folder,
        "batch_root": app.batch_root_folder,
        "batch_audio": app.batch_audio_folder,
        "batch_srt": app.batch_srt_folder,
        "music_single": app.music_file_single,
        "music_folder": app.music_folder_path,
        "output": app.output_folder,
        "subtitle_font": app.subtitle_font_file,
        "ffmpeg_path": app.ffmpeg_path_var,
        "png_overlay": app.png_overlay_path_var,
        "effect_overlay": app.effect_overlay_path_var,
        "presenter_video": app.presenter_video_path_var,
        "batch_mixed_media_folder": app.batch_mixed_media_folder,
    }


def initialize_state(app: Any) -> None:
    app.is_processing = False
    app.cancel_requested = threading.Event()
    app.progress_queue = queue.Queue()
    app.thread_executor = ThreadPoolExecutor(max_workers=3)
    app.available_encoders_cache: Optional[List[str]] = None
    app.loaded_fonts = []
    app.presenter_processed_frame_path = None
    app.download_thread = None
    app.yt_dlp_engine_path = None
    app.downloader_total_items_expected = 0
    app.downloader_total_items_completed = 0


__all__ = ["initialize_variables", "initialize_state"]
