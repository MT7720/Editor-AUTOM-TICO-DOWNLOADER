"""Compat layer that re-exports the video-processing pipeline entry points."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from queue import Queue
from typing import Dict, List, Optional, Tuple
import threading

# --- IMPORTAÇÕES DE SEGURANÇA ---
from security.license_manager import require_license
# --------------------------------

from processing.process_manager import process_manager
from video_processing.intro import _combine_intro_with_main, _maybe_create_intro_clip
from video_processing.final_pass import _perform_final_pass
from video_processing.batch import (_run_batch_image_processing, _run_batch_mixed_processing,
                                  _run_batch_video_processing, _run_hierarchical_batch_image_processing)
from video_processing.shared import logger
from video_processing.utils import _process_images_in_chunks

# Reexportações foram omitidas para brevidade, mas devem ser mantidas
__all__ = [
    "process_entrypoint",
    "process_manager",
]


def _gather_music_paths(entry: Dict[str, str]) -> List[str]:
    music = entry.get('music_file_single')
    if not music: return []
    return [path for path in (list(music) if isinstance(music, (list, tuple)) else [music]) if path and os.path.isfile(path)]


def _process_single_video(params: Dict, temp_dir: str, progress_queue: Queue, cancel_event: threading.Event) -> bool:
    base_video = params.get('media_path_single')
    if not (base_video and os.path.isfile(base_video)):
        progress_queue.put(("status", "[process_entrypoint] Vídeo base inválido.", "error"))
        return False

    narration_path = params.get('narration_file_single') if os.path.isfile(params.get('narration_file_single', '')) else None
    music_paths = _gather_music_paths(params)
    subtitle_path = params.get('subtitle_file_single') if os.path.isfile(params.get('subtitle_file_single', '')) else None

    progress_queue.put(("status", "[process_entrypoint] Iniciando renderização...", "info"))
    return _perform_final_pass(params, base_video, narration_path, music_paths, subtitle_path, progress_queue, cancel_event, temp_dir, "Renderização Única")


def _process_single_slideshow(params: Dict, temp_dir: str, progress_queue: Queue, cancel_event: threading.Event) -> bool:
    image_folder = params.get('media_path_single')
    if not (image_folder and os.path.isdir(image_folder)):
        progress_queue.put(("status", "[process_entrypoint] Pasta de imagens inválida.", "error"))
        return False

    supported = {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}
    images = [p for p in Path(image_folder).iterdir() if p.is_file() and p.suffix.lower() in supported]
    if not images:
        progress_queue.put(("status", "[process_entrypoint] Nenhuma imagem encontrada.", "error"))
        return False

    progress_queue.put(("status", f"[process_entrypoint] Preparando slideshow com {len(images)} imagens...", "info"))
    slideshow_path, success = _process_images_in_chunks(params, images, 0, temp_dir, progress_queue, cancel_event, "Slideshow Único")
    if not success or cancel_event.is_set(): return False

    narration_path = params.get('narration_file_single') if os.path.isfile(params.get('narration_file_single', '')) else None
    music_paths = _gather_music_paths(params)
    subtitle_path = params.get('subtitle_file_single') if os.path.isfile(params.get('subtitle_file_single', '')) else None
    
    return _perform_final_pass(params, slideshow_path, narration_path, music_paths, subtitle_path, progress_queue, cancel_event, temp_dir, "Slideshow Único")


@require_license # <<<<<<< DECORADOR DE SEGURANÇA APLICADO
def process_entrypoint(params: Dict, progress_queue: Queue, cancel_event: threading.Event) -> bool:
    """Ponto de entrada principal, agora protegido por verificação de licença."""
    temp_dir = tempfile.mkdtemp(prefix="kyle-editor-")
    mode = params.get('media_type', 'video_single')
    logger.info("[process_entrypoint] Processamento iniciado. Modo: %s", mode)
    success = False

    try:
        if cancel_event.is_set():
            progress_queue.put(("status", "[process_entrypoint] Cancelado antes do início.", "warning"))
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
            progress_queue.put(("status", f"Tipo de mídia desconhecido: {mode}", "error"))
            return False

        progress_queue.put(("finish", success))
        return success
    except Exception as exc:
        logger.exception("[process_entrypoint] Falha inesperada: %s", exc)
        progress_queue.put(("status", f"Erro inesperado: {exc}", "error"))
        progress_queue.put(("finish", False))
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info("[process_entrypoint] Finalizado. Sucesso: %s, Cancelado: %s", success, cancel_event.is_set())
