"""Compat layer that re-exports the video-processing pipeline entry points.

Historically the entire processing logic lived in this single module.  To make
maintenance tractable the implementation now lives in the ``video_processing``
package.  This file keeps the public API stable for the GUI and the test-suite
while delegating the heavy lifting to the new modules.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from queue import Queue
from typing import Dict, List, Optional, Tuple
import threading

from processing.process_manager import process_manager

from video_processing.intro import (
    _combine_intro_with_main,
    _maybe_create_intro_clip,
    _prepare_intro_text,
    _resolve_intro_text,
)
from video_processing.final_pass import _perform_final_pass
from video_processing.batch import (
    _get_music_playlist,
    _run_batch_image_processing,
    _run_batch_mixed_processing,
    _run_batch_video_processing,
    _run_hierarchical_batch_image_processing,
)
from video_processing.shared import (
    Image,
    ImageDraw,
    ImageFile,
    ImageFont,
    LANGUAGE_ALIASES,
    LANGUAGE_CODE_MAP,
    LANGUAGE_TRANSLATION_CODES,
    _attempt_translate_text,
    _create_typing_intro_clip,
    _escape_ffmpeg_path,
    _execute_ffmpeg,
    _get_codec_params,
    _infer_language_code_from_filename,
    _infer_language_code_from_name,
    _normalize_language_code,
    _probe_media_properties,
    _wrap_text_to_width,
    logger,
)
from video_processing.utils import (
    _build_subtitle_style_string,
    _create_concatenated_audio,
    _create_styled_ass_from_srt,
    _parse_resolution,
    _process_images_in_chunks,
)

__all__ = [
    "Image",
    "ImageDraw",
    "ImageFile",
    "ImageFont",
    "LANGUAGE_ALIASES",
    "LANGUAGE_CODE_MAP",
    "LANGUAGE_TRANSLATION_CODES",
    "_attempt_translate_text",
    "_build_subtitle_style_string",
    "_combine_intro_with_main",
    "_create_concatenated_audio",
    "_create_styled_ass_from_srt",
    "_create_typing_intro_clip",
    "_escape_ffmpeg_path",
    "_execute_ffmpeg",
    "_get_codec_params",
    "_get_music_playlist",
    "_infer_language_code_from_filename",
    "_infer_language_code_from_name",
    "_maybe_create_intro_clip",
    "_normalize_language_code",
    "_parse_resolution",
    "_perform_final_pass",
    "_prepare_intro_text",
    "_process_images_in_chunks",
    "_probe_media_properties",
    "_resolve_intro_text",
    "_wrap_text_to_width",
    "process_entrypoint",
    "process_manager",
]


def _gather_music_paths(entry: Dict[str, str]) -> List[str]:
    music = entry.get('music_file_single')
    if not music:
        return []
    if isinstance(music, (list, tuple)):
        candidates = list(music)
    else:
        candidates = [music]
    return [path for path in candidates if path and os.path.isfile(path)]


def _process_single_video(
    params: Dict,
    temp_dir: str,
    progress_queue: Queue,
    cancel_event: threading.Event,
) -> bool:
    base_video = params.get('media_path_single')
    if not base_video or not os.path.isfile(base_video):
        progress_queue.put(("status", "[process_entrypoint] Vídeo base inválido.", "error"))
        return False

    narration_path = params.get('narration_file_single')
    if narration_path and not os.path.isfile(narration_path):
        narration_path = None

    music_paths = _gather_music_paths(params)
    subtitle_path = params.get('subtitle_file_single') or None
    if subtitle_path and not os.path.isfile(subtitle_path):
        subtitle_path = None

    progress_queue.put(("status", "[process_entrypoint] Iniciando renderização do vídeo único...", "info"))
    return _perform_final_pass(
        params=params,
        base_video_path=base_video,
        narration_path=narration_path,
        music_paths=music_paths,
        subtitle_path=subtitle_path,
        progress_queue=progress_queue,
        cancel_event=cancel_event,
        temp_dir=temp_dir,
        log_prefix="Renderização Única",
    )


def _process_single_slideshow(
    params: Dict,
    temp_dir: str,
    progress_queue: Queue,
    cancel_event: threading.Event,
) -> bool:
    image_folder = params.get('media_path_single')
    if not image_folder or not os.path.isdir(image_folder):
        progress_queue.put(("status", "[process_entrypoint] Pasta de imagens inválida.", "error"))
        return False

    supported_ext = {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}
    images = [p for p in Path(image_folder).iterdir() if p.is_file() and p.suffix.lower() in supported_ext]
    if not images:
        progress_queue.put(("status", "[process_entrypoint] Nenhuma imagem encontrada na pasta selecionada.", "error"))
        return False

    progress_queue.put(("status", f"[process_entrypoint] Preparando slideshow com {len(images)} imagens...", "info"))
    slideshow_path, success = _process_images_in_chunks(
        params,
        images,
        final_duration=0,
        temp_dir=temp_dir,
        progress_queue=progress_queue,
        cancel_event=cancel_event,
        log_prefix="Slideshow Único",
    )

    if not success or cancel_event.is_set():
        return False

    narration_path = params.get('narration_file_single')
    if narration_path and not os.path.isfile(narration_path):
        narration_path = None

    music_paths = _gather_music_paths(params)
    subtitle_path = params.get('subtitle_file_single') or None
    if subtitle_path and not os.path.isfile(subtitle_path):
        subtitle_path = None

    return _perform_final_pass(
        params=params,
        base_video_path=slideshow_path,
        narration_path=narration_path,
        music_paths=music_paths,
        subtitle_path=subtitle_path,
        progress_queue=progress_queue,
        cancel_event=cancel_event,
        temp_dir=temp_dir,
        log_prefix="Slideshow Único",
    )


def process_entrypoint(params: Dict, progress_queue: Queue, cancel_event: threading.Event) -> bool:
    """Ponto de entrada principal utilizado pelo aplicativo gráfico."""

    temp_dir = tempfile.mkdtemp(prefix="kyle-editor-")
    mode = params.get('media_type', 'video_single')
    logger.info("[process_entrypoint] Processamento iniciado. Dir temporário: %s", temp_dir)
    success = False

    try:
        if cancel_event.is_set():
            progress_queue.put(("status", "[process_entrypoint] Cancelamento solicitado antes do início.", "warning"))
            return False

        if mode == 'video_single':
            success = _process_single_video(params, temp_dir, progress_queue, cancel_event)
        elif mode == 'image_folder':
            success = _process_single_slideshow(params, temp_dir, progress_queue, cancel_event)
        elif mode == 'batch_video':
            success = _run_batch_video_processing(params, progress_queue, cancel_event, temp_dir)
        elif mode == 'batch_image':
            success = _run_batch_image_processing(params, progress_queue, cancel_event, temp_dir)
        elif mode == 'batch_mixed':
            success = _run_batch_mixed_processing(params, progress_queue, cancel_event, temp_dir)
        elif mode == 'batch_image_hierarchical':
            success = _run_hierarchical_batch_image_processing(params, progress_queue, cancel_event, temp_dir)
        else:
            progress_queue.put(("status", f"[process_entrypoint] Tipo de mídia desconhecido: {mode}", "error"))
            success = False

        progress_queue.put(("finish", success))
        return success
    except Exception as exc:  # pragma: no cover - salvaguarda
        logger.exception("[process_entrypoint] Falha inesperada: %s", exc)
        progress_queue.put(("status", f"[process_entrypoint] Erro inesperado: {exc}", "error"))
        progress_queue.put(("finish", False))
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info("[process_entrypoint] Processamento finalizado. Sucesso: %s, Cancelado: %s", success, cancel_event.is_set())

