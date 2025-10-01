"""Batch-oriented helpers extracted from ``video_processing_logic``."""

from __future__ import annotations

import os
import random
import shutil
import tempfile
import threading
from pathlib import Path
from queue import Queue
from typing import Any, Dict, List, Optional, Tuple

from .final_pass import _perform_final_pass
from .shared import (
    _execute_ffmpeg,
    _infer_language_code_from_filename,
    _infer_language_code_from_name,
    _normalize_language_code,
    _probe_media_properties,
    logger,
)
from .utils import (
    _create_concatenated_audio,
    _get_music_playlist,
    _parse_resolution,
    _process_images_in_chunks,
)

__all__ = [
    "_run_batch_video_processing",
    "_run_batch_image_processing",
    "_run_batch_mixed_processing",
    "_run_hierarchical_batch_image_processing",
    "_get_music_playlist",
]


def _run_batch_video_processing(params: Dict[str, Any], progress_queue: Queue, cancel_event: threading.Event, temp_dir: str) -> bool:
    if cancel_event.is_set():
        return False

    audio_folder = params.get('batch_audio_folder')
    video_parent_folder = params.get('batch_video_parent_folder')
    srt_folder = params.get('batch_srt_folder')
    music_folder = params.get('music_folder_path')

    lang_code_to_folder_name_map = {
        "ALE": "Alemão", "BUL": "Búlgaro", "ESP": "Espanhol", "FRAN": "Francês", "GREGO": "Grego",
        "HOLAND": "Holandês", "ING": "Inglês", "ITA": "Italiano", "POL": "Polonês", "PT": "Português", "ROM": "Romeno"
    }

    if not audio_folder or not os.path.isdir(audio_folder):
        progress_queue.put(("status", "Erro: Pasta de áudios do lote inválida.", "error"))
        return False
    if not video_parent_folder or not os.path.isdir(video_parent_folder):
        progress_queue.put(("status", "Erro: Pasta de vídeos do lote inválida.", "error"))
        return False

    audio_files = sorted([f for f in os.listdir(audio_folder) if os.path.isfile(os.path.join(audio_folder, f)) and f.lower().endswith(('.mp3', '.wav', '.aac'))])
    if not audio_files:
        progress_queue.put(("status", "Erro: Nenhum arquivo de áudio encontrado na pasta de lote.", "error"))
        return False

    available_music_files: List[str] = []
    if music_folder and os.path.isdir(music_folder):
        try:
            music_ext = ('.mp3', '.wav', '.aac', '.flac', '.ogg')
            available_music_files = [os.path.join(music_folder, f) for f in os.listdir(music_folder) if os.path.isfile(os.path.join(music_folder, f)) and f.lower().endswith(music_ext)]
            if available_music_files:
                progress_queue.put(("status", f"{len(available_music_files)} músicas de fundo carregadas.", "info"))
        except OSError as e:
            progress_queue.put(("status", f"Aviso: Não foi possível ler a pasta de músicas: {e}", "warning"))

    try:
        video_subfolders = [d for d in os.listdir(video_parent_folder) if os.path.isdir(os.path.join(video_parent_folder, d))]
    except OSError as e:
        progress_queue.put(("status", f"Erro ao ler subpastas de vídeo: {e}", "error"))
        return False

    total_files = len(audio_files)
    for i, audio_filename in enumerate(audio_files):
        if cancel_event.is_set():
            return False

        progress_queue.put(("batch_progress", (i) / total_files))
        log_prefix = f"Lote Vídeo {i+1}/{total_files}"
        progress_queue.put(("status", f"--- Iniciando {log_prefix}: {audio_filename} ---", "info"))

        try:
            parts = Path(audio_filename).stem.split()
            if len(parts) < 2:
                raise IndexError("Formato de nome de arquivo inválido.")
            lang_code = _normalize_language_code(parts[1]) or parts[1].upper()
            language_name = lang_code_to_folder_name_map.get(lang_code)
            if not language_name:
                progress_queue.put(("status", f"[{log_prefix}] Aviso: Código '{lang_code}' não mapeado. Pulando.", "warning"))
                continue
        except IndexError:
            progress_queue.put(("status", f"[{log_prefix}] Aviso: Nome de áudio '{audio_filename}' inválido. Pulando.", "warning"))
            continue

        target_video_folder = next((os.path.join(video_parent_folder, d) for d in video_subfolders if d.lower().startswith(language_name.lower())), None)

        if not target_video_folder:
            progress_queue.put(("status", f"[{log_prefix}] Aviso: Pasta de vídeo para '{language_name}' não encontrada. Pulando.", "warning"))
            continue

        try:
            available_videos = sorted([os.path.join(target_video_folder, f) for f in os.listdir(target_video_folder) if f.lower().endswith(('.mp4', '.mov', '.mkv', '.avi'))])
        except OSError as e:
            progress_queue.put(("status", f"[{log_prefix}] Erro ao ler vídeos de '{target_video_folder}': {e}. Pulando.", "error"))
            continue

        if not available_videos:
            progress_queue.put(("status", f"[{log_prefix}] Aviso: Nenhum vídeo encontrado em '{target_video_folder}'. Pulando.", "warning"))
            continue

        subtitle_file = None
        if srt_folder and os.path.isdir(srt_folder):
            potential_srt = os.path.join(srt_folder, f"{Path(audio_filename).stem}.srt")
            if os.path.isfile(potential_srt):
                subtitle_file = potential_srt

        item_temp_dir = tempfile.mkdtemp(prefix=f"kyle-batch-vid-item-{i}-", dir=temp_dir)

        music_files_for_pass: List[str] = []
        if available_music_files:
            narration_full_path = os.path.join(audio_folder, audio_filename)
            narration_props = _probe_media_properties(narration_full_path, params['ffmpeg_path'])
            target_duration = float(narration_props['format']['duration']) if narration_props else 0
            if params.get('add_fade_out'):
                target_duration += params.get('fade_out_duration', 10)

            music_playlist = _get_music_playlist(available_music_files, target_duration, params, params['ffmpeg_path'])
            if len(music_playlist) > 1:
                concatenated_music_path = os.path.join(item_temp_dir, "concatenated_music.m4a")
                if _create_concatenated_audio(music_playlist, concatenated_music_path, item_temp_dir, params, cancel_event, progress_queue, log_prefix):
                    music_files_for_pass = [concatenated_music_path]
                else:
                    progress_queue.put(("status", f"[{log_prefix}] Falha ao concatenar músicas, usando apenas a primeira.", "warning"))
                    music_files_for_pass = [music_playlist[0]]
            else:
                music_files_for_pass = music_playlist

        final_pass_params = {**params,
            'output_filename_single': f"video_final_{Path(audio_filename).stem}.mp4"
        }
        final_pass_params['current_language_code'] = lang_code

        normalized_lang = _normalize_language_code(lang_code) or _normalize_language_code(language_name)
        if normalized_lang:
            final_pass_params['current_language_code'] = normalized_lang

        final_success = _perform_final_pass(
            params=final_pass_params,
            base_video_path=random.choice(available_videos),
            narration_path=os.path.join(audio_folder, audio_filename),
            music_paths=music_files_for_pass,
            subtitle_path=subtitle_file,
            progress_queue=progress_queue,
            cancel_event=cancel_event,
            temp_dir=item_temp_dir,
            log_prefix=log_prefix
        )
        shutil.rmtree(item_temp_dir)

        if not final_success and not cancel_event.is_set():
            progress_queue.put(("status", f"[{log_prefix}] Falha ao processar o item. Continuando...", "error"))

    progress_queue.put(("batch_progress", 1.0))
    return True


def _run_batch_image_processing(params: Dict[str, Any], progress_queue: Queue, cancel_event: threading.Event, temp_dir: str) -> bool:
    if cancel_event.is_set():
        return False

    audio_folder = params.get('batch_audio_folder')
    image_folder = params.get('batch_image_parent_folder')
    srt_folder = params.get('batch_srt_folder')
    music_folder = params.get('music_folder_path')

    if not audio_folder or not os.path.isdir(audio_folder):
        progress_queue.put(("status", "Erro: Pasta de áudios do lote inválida.", "error"))
        return False
    if not image_folder or not os.path.isdir(image_folder):
        progress_queue.put(("status", "Erro: Pasta de imagens do lote inválida.", "error"))
        return False

    audio_files = sorted([f for f in os.listdir(audio_folder) if os.path.isfile(os.path.join(audio_folder, f)) and f.lower().endswith(('.mp3', '.wav', '.aac'))])
    if not audio_files:
        progress_queue.put(("status", "Erro: Nenhum arquivo de áudio encontrado na pasta de lote.", "error"))
        return False

    supported_ext = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
    all_images = [p for p in Path(image_folder).iterdir() if p.is_file() and p.suffix.lower() in supported_ext]
    if not all_images:
        progress_queue.put(("status", f"Erro: Nenhuma imagem encontrada na pasta de imagens selecionada: {image_folder}", "error"))
        return False

    available_music_files: List[str] = []
    if music_folder and os.path.isdir(music_folder):
        try:
            music_ext = ('.mp3', '.wav', '.aac', '.flac', '.ogg')
            available_music_files = [os.path.join(music_folder, f) for f in os.listdir(music_folder) if f.lower().endswith(music_ext)]
            if available_music_files:
                progress_queue.put(("status", f"{len(available_music_files)} músicas de fundo carregadas.", "info"))
        except OSError as e:
            progress_queue.put(("status", f"Aviso: Não foi possível ler a pasta de músicas: {e}", "warning"))

    total_files = len(audio_files)
    for i, audio_filename in enumerate(audio_files):
        if cancel_event.is_set():
            return False

        progress_queue.put(("batch_progress", (i) / total_files))
        log_prefix = f"Lote Imagem {i+1}/{total_files}"
        progress_queue.put(("status", f"--- Iniciando {log_prefix}: {audio_filename} ---", "info"))

        narration_path = os.path.join(audio_folder, audio_filename)
        narration_props = _probe_media_properties(narration_path, params['ffmpeg_path'])
        if not narration_props or 'format' not in narration_props or 'duration' not in narration_props['format']:
            progress_queue.put(("status", f"[{log_prefix}] Erro: Não foi possível ler duração de '{audio_filename}'. Pulando.", "error"))
            continue

        final_duration = float(narration_props['format']['duration'])
        if params.get('add_fade_out'):
            final_duration += params.get('fade_out_duration', 10)

        images_for_this_video = all_images.copy()
        random.shuffle(images_for_this_video)
        progress_queue.put(("status", f"[{log_prefix}] {len(images_for_this_video)} imagens embaralhadas para este vídeo.", "info"))

        item_temp_dir = tempfile.mkdtemp(prefix=f"kyle-batch-img-item-{i}-", dir=temp_dir)
        base_video_path, success = _process_images_in_chunks(params, images_for_this_video, final_duration, item_temp_dir, progress_queue, cancel_event, log_prefix)

        if not success:
            if not cancel_event.is_set():
                progress_queue.put(("status", f"[{log_prefix}] Falha ao gerar vídeo base. Continuando...", "error"))
            shutil.rmtree(item_temp_dir)
            continue

        if cancel_event.is_set():
            return False

        progress_queue.put(("status", f"[{log_prefix}] Adicionando áudios e legendas...", "info"))

        subtitle_file = None
        if srt_folder and os.path.isdir(srt_folder):
            potential_srt = os.path.join(srt_folder, f"{Path(audio_filename).stem}.srt")
            if os.path.isfile(potential_srt):
                subtitle_file = potential_srt

        music_files_for_pass: List[str] = []
        if available_music_files:
            music_playlist = _get_music_playlist(available_music_files, final_duration, params, params['ffmpeg_path'])
            if len(music_playlist) > 1:
                concatenated_music_path = os.path.join(item_temp_dir, "concatenated_music.m4a")
                if _create_concatenated_audio(music_playlist, concatenated_music_path, item_temp_dir, params, cancel_event, progress_queue, log_prefix):
                    music_files_for_pass = [concatenated_music_path]
                else:
                    progress_queue.put(("status", f"[{log_prefix}] Falha ao concatenar músicas, usando apenas a primeira.", "warning"))
                    music_files_for_pass = [music_playlist[0]]
            else:
                music_files_for_pass = music_playlist

        language_guess = _infer_language_code_from_name(Path(audio_filename).stem)
        if not language_guess and subtitle_file:
            language_guess = _infer_language_code_from_name(Path(subtitle_file).stem)

        final_pass_params = {**params, 'output_filename_single': f"video_final_{Path(audio_filename).stem}.mp4"}
        final_pass_params['current_language_code'] = language_guess

        inferred_lang = _infer_language_code_from_filename(audio_filename)
        if inferred_lang:
            final_pass_params['current_language_code'] = inferred_lang

        final_success = _perform_final_pass(
            params=final_pass_params,
            base_video_path=base_video_path,
            narration_path=narration_path,
            music_paths=music_files_for_pass,
            subtitle_path=subtitle_file,
            progress_queue=progress_queue,
            cancel_event=cancel_event,
            temp_dir=item_temp_dir,
            log_prefix=log_prefix
        )

        if not final_success and not cancel_event.is_set():
            progress_queue.put(("status", f"[{log_prefix}] Falha ao finalizar o vídeo. Continuando...", "error"))

        shutil.rmtree(item_temp_dir)

    progress_queue.put(("batch_progress", 1.0))
    return True


def _run_batch_mixed_processing(params: Dict[str, Any], progress_queue: Queue, cancel_event: threading.Event, temp_dir: str) -> bool:
    if cancel_event.is_set():
        return False

    log_prefix_main = "Lote Misto"

    audio_folder = params.get('batch_audio_folder')
    mixed_media_folder = params.get('batch_mixed_media_folder')
    srt_folder = params.get('batch_srt_folder')
    music_folder = params.get('music_folder_path')

    if not audio_folder or not os.path.isdir(audio_folder):
        progress_queue.put(("status", f"[{log_prefix_main}] Erro: Pasta de áudios do lote inválida.", "error"))
        return False
    if not mixed_media_folder or not os.path.isdir(mixed_media_folder):
        progress_queue.put(("status", f"[{log_prefix_main}] Erro: Pasta de mídia (vídeos/imagens) inválida.", "error"))
        return False

    progress_queue.put(("status", f"[{log_prefix_main}] Analisando pasta de mídia para criar vídeo base...", "info"))
    all_files = list(Path(mixed_media_folder).iterdir())
    supported_img_ext = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
    supported_vid_ext = ('.mp4', '.mov', '.mkv', '.avi')
    images = sorted([p for p in all_files if p.is_file() and p.suffix.lower() in supported_img_ext])
    videos = sorted([p for p in all_files if p.is_file() and p.suffix.lower() in supported_vid_ext])

    if not images and not videos:
        progress_queue.put(("status", f"[{log_prefix_main}] Erro: Nenhuma imagem ou vídeo encontrado em {mixed_media_folder}", "error"))
        return False
    progress_queue.put(("status", f"[{log_prefix_main}] Encontrados {len(videos)} vídeos e {len(images)} imagens.", "info"))

    base_video_path = None
    base_video_creation_temp_dir = tempfile.mkdtemp(prefix="kyle-base-video-", dir=temp_dir)

    try:
        files_to_concat_ts: List[str] = []
        w, h = _parse_resolution(params['resolution'])

        if videos:
            progress_queue.put(("status", f"[{log_prefix_main}] Padronizando vídeos para montagem...", "info"))
            for idx, video_path in enumerate(videos):
                if cancel_event.is_set():
                    raise InterruptedError()
                ts_path = os.path.join(base_video_creation_temp_dir, f"vid_{idx}.ts")
                cmd_reencode = [
                    params['ffmpeg_path'], '-y', '-i', str(video_path),
                    '-c:v', 'libx264', '-preset', 'medium', '-crf', '23',
                    '-vf', f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1",
                    '-c:a', 'aac', '-b:a', '192k',
                    ts_path
                ]
                progress_queue.put(("status", f"[{log_prefix_main}] Processando vídeo {idx+1}/{len(videos)}: {video_path.name}", "info"))
                if not _execute_ffmpeg(cmd_reencode, 1, None, cancel_event, f"{log_prefix_main} (Vídeo {idx+1})", progress_queue):
                    raise ValueError(f"Falha ao padronizar o vídeo {video_path.name}")
                files_to_concat_ts.append(ts_path)

        if images:
            progress_queue.put(("status", f"[{log_prefix_main}] Gerando slideshow a partir das imagens...", "info"))
            img_duration = params.get('image_duration', 5)
            slideshow_duration = (len(images) * img_duration)
            slideshow_temp_dir = tempfile.mkdtemp(prefix="kyle-slideshow-", dir=base_video_creation_temp_dir)

            slideshow_mp4_path, success = _process_images_in_chunks(params, images, slideshow_duration, slideshow_temp_dir, progress_queue, cancel_event, f"{log_prefix_main} (Slideshow)")
            if not success:
                raise ValueError("Falha ao gerar o slideshow a partir das imagens.")

            slideshow_ts_path = os.path.join(base_video_creation_temp_dir, "slideshow.ts")
            cmd_reencode_ss = [params['ffmpeg_path'], '-y', '-i', slideshow_mp4_path, '-c', 'copy', slideshow_ts_path]
            if not _execute_ffmpeg(cmd_reencode_ss, 1, None, cancel_event, f"{log_prefix_main} (Conv. Slideshow)", progress_queue):
                raise ValueError("Falha ao converter slideshow para formato de montagem.")
            files_to_concat_ts.append(slideshow_ts_path)

        if not files_to_concat_ts:
            raise ValueError("Nenhum clipe de vídeo foi gerado para a montagem.")

        progress_queue.put(("status", f"[{log_prefix_main}] Montando vídeo base final...", "info"))
        concat_list_path = os.path.join(base_video_creation_temp_dir, 'concat_list.txt')
        with open(concat_list_path, 'w', encoding='utf-8') as f:
            for path in files_to_concat_ts:
                f.write(f"file '{Path(path).as_posix()}'\n")

        base_video_path = os.path.normpath(os.path.join(base_video_creation_temp_dir, "combined_base_video.mp4"))
        cmd_concat = [params['ffmpeg_path'], '-y', '-f', 'concat', '-safe', '0', '-i', concat_list_path, '-c', 'copy', base_video_path]
        if not _execute_ffmpeg(cmd_concat, 1, None, cancel_event, f"{log_prefix_main} (Montagem)", progress_queue):
            raise ValueError("Falha ao montar o vídeo base final.")

    except (ValueError, InterruptedError, Exception) as e:
        if not cancel_event.is_set():
            progress_queue.put(("status", f"[{log_prefix_main}] Erro ao criar vídeo base: {e}", "error"))
        shutil.rmtree(base_video_creation_temp_dir)
        return False

    audio_files = sorted([f for f in os.listdir(audio_folder) if os.path.isfile(os.path.join(audio_folder, f)) and f.lower().endswith(('.mp3', '.wav', '.aac'))])
    if not audio_files:
        progress_queue.put(("status", f"[{log_prefix_main}] Erro: Nenhum arquivo de áudio encontrado.", "error"))
        return False

    available_music_files: List[str] = []
    if music_folder and os.path.isdir(music_folder):
        music_ext = ('.mp3', '.wav', '.aac', '.flac', '.ogg')
        available_music_files = [os.path.join(music_folder, f) for f in os.listdir(music_folder) if f.lower().endswith(music_ext)]

    total_files = len(audio_files)
    for i, audio_filename in enumerate(audio_files):
        if cancel_event.is_set():
            break

        progress_queue.put(("batch_progress", (i) / total_files))
        log_prefix = f"Lote Misto {i+1}/{total_files}"
        progress_queue.put(("status", f"--- Iniciando {log_prefix}: {audio_filename} ---", "info"))

        narration_path = os.path.join(audio_folder, audio_filename)
        subtitle_file = None
        if srt_folder and os.path.isdir(srt_folder):
            potential_srt = os.path.join(srt_folder, f"{Path(audio_filename).stem}.srt")
            if os.path.isfile(potential_srt):
                subtitle_file = potential_srt

        item_temp_dir = tempfile.mkdtemp(prefix=f"kyle-mixed-item-{i}-", dir=temp_dir)

        music_files_for_pass: List[str] = []
        if available_music_files:
            narration_props = _probe_media_properties(narration_path, params['ffmpeg_path'])
            target_duration = float(narration_props['format']['duration']) if narration_props else 0
            if params.get('add_fade_out'):
                target_duration += params.get('fade_out_duration', 10)

            music_playlist = _get_music_playlist(available_music_files, target_duration, params, params['ffmpeg_path'])
            if len(music_playlist) > 1:
                concatenated_music_path = os.path.join(item_temp_dir, "concatenated_music.m4a")
                if _create_concatenated_audio(music_playlist, concatenated_music_path, item_temp_dir, params, cancel_event, progress_queue, log_prefix):
                    music_files_for_pass = [concatenated_music_path]
                else:
                    progress_queue.put(("status", f"[{log_prefix}] Falha ao concatenar músicas, usando apenas a primeira.", "warning"))
                    music_files_for_pass = [music_playlist[0]]
            else:
                music_files_for_pass = music_playlist

        language_guess = _infer_language_code_from_name(Path(audio_filename).stem)
        if not language_guess and subtitle_file:
            language_guess = _infer_language_code_from_name(Path(subtitle_file).stem)

        final_pass_params = {**params, 'output_filename_single': f"video_final_{Path(audio_filename).stem}.mp4"}
        final_pass_params['current_language_code'] = language_guess

        inferred_lang = _infer_language_code_from_filename(audio_filename)
        if inferred_lang:
            final_pass_params['current_language_code'] = inferred_lang

        _perform_final_pass(
            params=final_pass_params,
            base_video_path=base_video_path,
            narration_path=narration_path,
            music_paths=music_files_for_pass,
            subtitle_path=subtitle_file,
            progress_queue=progress_queue,
            cancel_event=cancel_event,
            temp_dir=item_temp_dir,
            log_prefix=log_prefix
        )
        shutil.rmtree(item_temp_dir)

    shutil.rmtree(base_video_creation_temp_dir)
    progress_queue.put(("batch_progress", 1.0))
    return not cancel_event.is_set()


def _run_hierarchical_batch_image_processing(params: Dict[str, Any], progress_queue: Queue, cancel_event: threading.Event, temp_dir: str) -> bool:
    if cancel_event.is_set():
        return False

    root_folder = params.get('batch_root_folder')
    image_folder = params.get('batch_image_parent_folder')
    music_folder = params.get('music_folder_path')

    if not root_folder or not os.path.isdir(root_folder):
        progress_queue.put(("status", "Erro: Pasta Raiz do lote inválida.", "error"))
        return False
    if not image_folder or not os.path.isdir(image_folder):
        progress_queue.put(("status", "Erro: Pasta de imagens do lote inválida.", "error"))
        return False

    progress_queue.put(("status", f"Buscando arquivos de áudio em subpastas de '{Path(root_folder).name}'...", "info"))
    audio_files_to_process: List[Path] = []
    try:
        audio_ext = ('.mp3', '.wav', '.aac')
        for f in Path(root_folder).rglob('*'):
            if f.is_file() and f.suffix.lower() in audio_ext:
                audio_files_to_process.append(f)

        audio_files_to_process.sort()
    except OSError as e:
        progress_queue.put(("status", f"Erro ao buscar arquivos de áudio: {e}", "error"))
        return False

    if not audio_files_to_process:
        progress_queue.put(("status", "Erro: Nenhum arquivo de áudio encontrado nas subpastas.", "error"))
        return False
    progress_queue.put(("status", f"Encontrados {len(audio_files_to_process)} arquivos de áudio para processar.", "info"))

    supported_img_ext = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
    all_images = [p for p in Path(image_folder).iterdir() if p.is_file() and p.suffix.lower() in supported_img_ext]
    if not all_images:
        progress_queue.put(("status", f"Erro: Nenhuma imagem encontrada em {image_folder}", "error"))
        return False

    available_music_files: List[str] = []
    if music_folder and os.path.isdir(music_folder):
        try:
            music_ext = ('.mp3', '.wav', '.aac', '.flac', '.ogg')
            available_music_files = [os.path.join(music_folder, f) for f in os.listdir(music_folder) if f.lower().endswith(music_ext)]
            if available_music_files:
                progress_queue.put(("status", f"{len(available_music_files)} músicas de fundo carregadas.", "info"))
        except OSError as e:
            progress_queue.put(("status", f"Aviso: Não foi possível ler a pasta de músicas: {e}", "warning"))

    total_files = len(audio_files_to_process)
    for i, audio_filepath in enumerate(audio_files_to_process):
        if cancel_event.is_set():
            return False

        progress_queue.put(("batch_progress", (i) / total_files))
        log_prefix = f"Lote Hierárquico {i+1}/{total_files}"
        progress_queue.put(("status", f"--- Iniciando {log_prefix}: {audio_filepath.name} ---", "info"))

        narration_path = str(audio_filepath)
        subtitle_path = audio_filepath.with_suffix('.srt')
        subtitle_file = str(subtitle_path) if subtitle_path.is_file() else None
        if subtitle_file:
            progress_queue.put(("status", f"[{log_prefix}] Legenda encontrada: {Path(subtitle_file).name}", "info"))

        narration_props = _probe_media_properties(narration_path, params['ffmpeg_path'])
        if not narration_props or 'format' not in narration_props or 'duration' not in narration_props['format']:
            progress_queue.put(("status", f"[{log_prefix}] Erro: Não foi possível ler duração de '{audio_filepath.name}'. Pulando.", "error"))
            continue

        final_duration = float(narration_props['format']['duration'])
        if params.get('add_fade_out'):
            final_duration += params.get('fade_out_duration', 10)

        images_for_this_video = all_images.copy()
        random.shuffle(images_for_this_video)

        item_temp_dir = tempfile.mkdtemp(prefix=f"kyle-h-batch-item-{i}-", dir=temp_dir)
        base_video_path, success = _process_images_in_chunks(params, images_for_this_video, final_duration, item_temp_dir, progress_queue, cancel_event, log_prefix)

        if not success:
            if not cancel_event.is_set():
                progress_queue.put(("status", f"[{log_prefix}] Falha ao gerar vídeo base. Pulando para o próximo item.", "error"))
            shutil.rmtree(item_temp_dir)
            continue

        if cancel_event.is_set():
            return False

        music_files_for_pass: List[str] = []
        if available_music_files:
            music_playlist = _get_music_playlist(available_music_files, final_duration, params, params['ffmpeg_path'])
            if len(music_playlist) > 1:
                concatenated_music_path = os.path.join(item_temp_dir, "concatenated_music.m4a")
                if _create_concatenated_audio(music_playlist, concatenated_music_path, item_temp_dir, params, cancel_event, progress_queue, log_prefix):
                    music_files_for_pass = [concatenated_music_path]
                else:
                    progress_queue.put(("status", f"[{log_prefix}] Falha ao concatenar músicas, usando apenas a primeira.", "warning"))
                    music_files_for_pass = [music_playlist[0]]
            else:
                music_files_for_pass = music_playlist

        language_guess = _infer_language_code_from_name(audio_filepath.stem)
        if not language_guess and subtitle_file:
            language_guess = _infer_language_code_from_name(Path(subtitle_file).stem)

        final_pass_params = {**params, 'output_filename_single': f"video_final_{audio_filepath.stem}.mp4"}
        final_pass_params['current_language_code'] = language_guess

        inferred_lang = _infer_language_code_from_filename(audio_filepath.name)
        if inferred_lang:
            final_pass_params['current_language_code'] = inferred_lang

        final_pass_params['mov_overlay_path'] = None
        final_pass_params['intro_phrase_text'] = ""
        final_pass_params['intro_phrase_enabled'] = False

        final_success = _perform_final_pass(
            params=final_pass_params,
            base_video_path=base_video_path,
            narration_path=narration_path,
            music_paths=music_files_for_pass,
            subtitle_path=subtitle_file,
            progress_queue=progress_queue,
            cancel_event=cancel_event,
            temp_dir=item_temp_dir,
            log_prefix=log_prefix
        )

        if not final_success and not cancel_event.is_set():
            progress_queue.put(("status", f"[{log_prefix}] Falha ao finalizar o vídeo. Continuando...", "error"))

        shutil.rmtree(item_temp_dir)

    progress_queue.put(("batch_progress", 1.0))
    return True
