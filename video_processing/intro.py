"""Intro clip handling logic extracted from ``video_processing_logic``."""

from __future__ import annotations

import threading
from queue import Queue
from typing import Any, Dict, List, Optional, Tuple

from .shared import (
    _attempt_translate_text,
    _create_typing_intro_clip,
    _execute_ffmpeg,
    _get_codec_params,
    _normalize_language_code,
    _probe_media_properties,
    LANGUAGE_CODE_MAP,
    logger,
)

__all__ = [
    "_prepare_intro_text",
    "_resolve_intro_text",
    "_maybe_create_intro_clip",
    "_combine_intro_with_main",
]


def _prepare_intro_text(
    params: Dict[str, Any],
    language_hint: Optional[str] = None,
    progress_queue: Optional[Queue] = None,
    log_prefix: str = "",
) -> Optional[Dict[str, Any]]:
    """Seleciona e traduz (se necessário) o texto de introdução apropriado."""

    if not params.get('intro_enabled'):
        return None

    intro_texts_raw = params.get('intro_texts') or {}
    intro_texts: Dict[str, str] = {}
    for key, value in intro_texts_raw.items():
        normalized_key = _normalize_language_code(key)
        if not normalized_key:
            continue
        cleaned = str(value or '').strip()
        if cleaned:
            intro_texts[normalized_key] = cleaned

    default_text = str(params.get('intro_default_text') or '').strip()
    if not intro_texts and not default_text:
        return None

    selected_language = (
        _normalize_language_code(language_hint)
        or _normalize_language_code(params.get('current_language_code'))
        or _normalize_language_code(params.get('intro_language_code'))
    )

    translation_applied = False
    base_language_code: Optional[str] = None
    base_text: str = ""

    if default_text:
        base_text = default_text
    elif intro_texts:
        base_language_code, base_text = next(iter(intro_texts.items()))

    if selected_language and selected_language in intro_texts:
        text_to_use = intro_texts[selected_language]
        final_language = selected_language
        language_label = LANGUAGE_CODE_MAP.get(final_language)
    elif base_text:
        text_to_use = base_text
        final_language = base_language_code
        language_label = (
            LANGUAGE_CODE_MAP.get(base_language_code)
            if base_language_code
            else "Padrão"
        )
        if selected_language:
            translated, translation_applied = _attempt_translate_text(base_text, selected_language)
            if translated:
                text_to_use = translated
                final_language = selected_language
                language_label = LANGUAGE_CODE_MAP.get(selected_language, "Padrão")
                if translation_applied:
                    language_label = f"{language_label} (traduzido)"
            elif progress_queue is not None and base_language_code != selected_language:
                progress_queue.put((
                    "status",
                    f"[{log_prefix}] Não foi possível traduzir a introdução para {LANGUAGE_CODE_MAP.get(selected_language, selected_language)}. Texto padrão será usado.",
                    "warning",
                ))
    else:
        return None

    return {
        'text': text_to_use.strip(),
        'language_code': final_language,
        'language_label': language_label or "Padrão",
        'translation_applied': translation_applied,
        'base_language_code': base_language_code,
    }


def _resolve_intro_text(params: Dict[str, Any], language_hint: Optional[str] = None) -> Optional[Dict[str, Any]]:
    intro_info = _prepare_intro_text(params, language_hint)
    if not intro_info:
        return None
    return {
        'text': intro_info['text'],
        'language_code': intro_info.get('language_code'),
        'language_label': intro_info.get('language_label', 'Padrão'),
        'translation_applied': intro_info.get('translation_applied', False),
    }


def _maybe_create_intro_clip(
    params: Dict[str, Any],
    temp_dir: str,
    resolution: Tuple[int, int],
    progress_queue: Queue,
    cancel_event: threading.Event,
    log_prefix: str,
) -> Optional[Dict[str, Any]]:

    intro_selection = _prepare_intro_text(
        params,
        language_hint=params.get('current_language_code'),
        progress_queue=progress_queue,
        log_prefix=log_prefix,
    )

    if not intro_selection:
        return None

    text_to_use = intro_selection['text']

    try:
        intro_info = _create_typing_intro_clip(text_to_use, resolution, params, temp_dir, progress_queue, cancel_event, log_prefix)
        if intro_info:
            intro_info['language_code'] = intro_selection.get('language_code')
            intro_info['language_label'] = intro_selection.get('language_label')
            intro_info['text'] = text_to_use
            intro_info['translation_applied'] = intro_selection.get('translation_applied', False)
        return intro_info
    except Exception as exc:
        logger.error(f"[{log_prefix}] Falha ao criar introdução digitada: {exc}", exc_info=True)
        progress_queue.put(("status", f"[{log_prefix}] Erro ao criar introdução digitada: {exc}", "error"))
        return None


def _combine_intro_with_main(
    intro_info: Dict[str, Any],
    main_content_path: str,
    final_output_path: str,
    params: Dict[str, Any],
    progress_queue: Queue,
    cancel_event: threading.Event,
    log_prefix: str,
) -> bool:

    intro_path = intro_info['path']
    intro_props = _probe_media_properties(intro_path, params['ffmpeg_path']) or {}
    main_props = _probe_media_properties(main_content_path, params['ffmpeg_path']) or {}

    intro_duration = float(intro_props.get('format', {}).get('duration', intro_info.get('duration', 0)))
    main_duration = float(main_props.get('format', {}).get('duration', 0))
    total_duration = intro_duration + main_duration

    fade_duration = 0.6
    if intro_duration > 0:
        fade_duration = min(fade_duration, intro_duration / 2)
    if main_duration > 0:
        fade_duration = min(fade_duration, main_duration / 2)
    fade_duration = max(0.3, fade_duration)
    typing_duration = float(intro_info.get('typing_duration', 0.0) or 0.0)
    hold_duration = float(intro_info.get('hold_duration', 0.0) or 0.0)
    post_hold_duration = float(intro_info.get('post_hold_duration', 0.0) or 0.0)
    desired_offset = typing_duration + hold_duration + post_hold_duration
    max_offset = max(0.0, intro_duration - fade_duration)
    if desired_offset > 0:
        offset = min(max_offset, desired_offset)
    else:
        offset = max_offset

    intro_has_audio = any(stream.get('codec_type') == 'audio' for stream in intro_props.get('streams', []))
    main_has_audio = any(stream.get('codec_type') == 'audio' for stream in main_props.get('streams', []))

    filter_parts = [
        f"[0:v][1:v]xfade=transition=fade:duration={fade_duration}:offset={offset}[vout]"
    ]

    map_args: List[str] = ['-map', '[vout]']
    audio_mapping_done = False

    if intro_has_audio and main_has_audio:
        filter_parts.append(f"[0:a][1:a]acrossfade=d={fade_duration}[aout]")
        map_args.extend(['-map', '[aout]'])
        audio_mapping_done = True
    elif intro_has_audio:
        filter_parts.append(f"[0:a]afade=t=out:st={offset}:d={fade_duration}[introa]")
        map_args.extend(['-map', '[introa]'])
        audio_mapping_done = True
    elif main_has_audio:
        filter_parts.append(f"[1:a]afade=t=in:st=0:d={fade_duration}[maina]")
        map_args.extend(['-map', '[maina]'])
        audio_mapping_done = True

    if not audio_mapping_done:
        map_args.extend(['-map', '0:a?', '-map', '1:a?'])

    filter_complex = ';'.join(filter_parts)

    progress_queue.put(("status", f"[{log_prefix}] Combinando introdução com o vídeo principal...", "info"))

    base_cmd = [
        params['ffmpeg_path'], '-y',
        '-i', intro_path,
        '-i', main_content_path,
        '-filter_complex', filter_complex,
        *map_args,
    ]

    codec_attempts: List[Tuple[str, List[str]]] = []

    def codec_label(codec_params: List[str]) -> str:
        if any(enc in codec_params for enc in ('h264_nvenc', 'hevc_nvenc')):
            return 'GPU (NVENC)'
        if any(enc in codec_params for enc in ('libx264', 'libx265')):
            return 'CPU (libx264)'
        if 'copy' in codec_params:
            return 'Cópia direta'
        return 'Encoder padrão'

    primary_codec_params = _get_codec_params(params, True)
    codec_attempts.append((codec_label(primary_codec_params), primary_codec_params))

    if any(enc in primary_codec_params for enc in ('h264_nvenc', 'hevc_nvenc')):
        cpu_params = params.copy()
        cpu_params['video_codec'] = 'CPU (libx264)'
        fallback_params = _get_codec_params(cpu_params, True)
        codec_attempts.append((codec_label(fallback_params), fallback_params))

    audio_args = ['-c:a', 'aac', '-b:a', '192k'] if audio_mapping_done else ['-c:a', 'copy']

    time_args: List[str] = []
    if total_duration > 0:
        time_args.extend(['-t', f"{total_duration:.6f}"])
    time_args.append('-shortest')

    output_args = ['-movflags', '+faststart', final_output_path]

    def merge_progress(pct: float) -> None:
        progress_queue.put(("progress", min(1.0, pct)))

    success = False
    total_attempts = len(codec_attempts)

    for attempt_idx, (label, codec_params) in enumerate(codec_attempts, start=1):
        cmd_merge = [*base_cmd, *codec_params, *audio_args, *time_args, *output_args]

        success = _execute_ffmpeg(
            cmd_merge,
            total_duration or intro_info.get('duration', 5),
            merge_progress,
            cancel_event,
            f"{log_prefix} (Intro Merge - {label})",
            progress_queue,
        )

        if success or cancel_event.is_set():
            break

        if attempt_idx < total_attempts:
            progress_queue.put((
                "status",
                f"[{log_prefix}] Falha ao mesclar com {label}. Alternando encoder...",
                "warning",
            ))

    return success
