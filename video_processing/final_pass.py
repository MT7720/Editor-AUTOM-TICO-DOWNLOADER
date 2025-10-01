"""Final rendering stage extracted from ``video_processing_logic``."""

from __future__ import annotations

import os
from pathlib import Path
from queue import Queue
from typing import Any, Dict, List, Optional, Tuple
import threading

from .intro import _maybe_create_intro_clip, _combine_intro_with_main
from .shared import (
    _escape_ffmpeg_path,
    _execute_ffmpeg,
    _get_codec_params,
    _probe_media_properties,
    logger,
)
from .utils import _parse_resolution, _create_styled_ass_from_srt

__all__ = ["_perform_final_pass"]


def _perform_final_pass(
    params: Dict,
    base_video_path: str,
    narration_path: Optional[str],
    music_paths: List[str],
    subtitle_path: Optional[str],
    progress_queue: Queue,
    cancel_event: threading.Event,
    temp_dir: str,
    log_prefix: str,
) -> bool:

    if not base_video_path or not os.path.exists(base_video_path):
        progress_queue.put(("status", f"[{log_prefix}] Erro Interno: Arquivo de vídeo base não foi encontrado.", "error"))
        return False

    narration_duration = 0.0
    narration_props = _probe_media_properties(narration_path, params['ffmpeg_path']) if narration_path and os.path.isfile(narration_path) else None
    if narration_props and 'format' in narration_props and 'duration' in narration_props['format']:
        try:
            narration_duration = float(narration_props['format']['duration'])
        except (TypeError, ValueError):
            narration_duration = 0.0

    base_video_duration = 0.0
    video_props = _probe_media_properties(base_video_path, params['ffmpeg_path'])
    if video_props and 'format' in video_props and 'duration' in video_props['format']:
        try:
            base_video_duration = float(video_props['format']['duration'])
        except (TypeError, ValueError):
            base_video_duration = 0.0

    content_duration = max(narration_duration, base_video_duration, 0.0)
    if content_duration <= 0:
        progress_queue.put(("status", f"[{log_prefix}] AVISO: Não foi possível determinar a duração do conteúdo.", "warning"))
        content_duration = 1.0

    fade_tail_duration = 0.0
    if params.get('add_fade_out'):
        try:
            fade_tail_duration = max(0.0, float(params.get('fade_out_duration', 10)))
        except (TypeError, ValueError):
            fade_tail_duration = 0.0

    narration_with_tail = narration_duration + fade_tail_duration if narration_duration > 0 else 0.0
    total_duration = max(content_duration, narration_with_tail)

    inputs: List[str] = []
    filter_complex_parts: List[str] = []
    map_args: List[str] = []
    input_map: Dict[str, int] = {}
    current_idx = 0

    inputs.extend(["-i", base_video_path])
    input_map['main_video'] = current_idx
    current_idx += 1
    last_video_stream = f"[{input_map['main_video']}:v]"

    if params.get('effect_overlay_path') and os.path.isfile(params['effect_overlay_path']):
        inputs.extend(["-stream_loop", "-1", "-i", params['effect_overlay_path']])
        input_map['effect'] = current_idx
        current_idx += 1
    if params.get('png_overlay_path') and os.path.isfile(params['png_overlay_path']):
        inputs.extend(["-i", params['png_overlay_path']])
        input_map['png'] = current_idx
        current_idx += 1
    if params.get('presenter_video_path') and os.path.isfile(params['presenter_video_path']):
        inputs.extend(["-stream_loop", "-1", "-i", params['presenter_video_path']])
        input_map['presenter'] = current_idx
        current_idx += 1

    if narration_path and os.path.isfile(narration_path):
        inputs.extend(["-i", narration_path])
        input_map['narration'] = current_idx
        current_idx += 1
    if music_paths and music_paths[0] and os.path.isfile(music_paths[0]):
        inputs.extend(["-i", music_paths[0]])
        input_map['music'] = current_idx
        current_idx += 1

    progress_queue.put(("status", f"[{log_prefix}] Construindo filtros de vídeo...", "info"))

    W, H = _parse_resolution(params['resolution'])
    intro_info = _maybe_create_intro_clip(params, temp_dir, (W, H), progress_queue, cancel_event, log_prefix)
    if intro_info:
        label = intro_info.get('language_label') or "Padrão"
        if intro_info.get('translation_applied'):
            label = f"{label} - tradução automática"
        progress_queue.put((
            "status",
            f"[{log_prefix}] Introdução digitada aplicada ({label}).",
            "info",
        ))

    filter_complex_parts.append(f"{last_video_stream}scale={W}:{H},setsar=1[v_scaled]")
    last_video_stream = "[v_scaled]"

    if 'effect' in input_map:
        blend_mode = params.get('effect_blend_mode', 'screen').lower()
        effect_opacity = float(params.get('effect_blend_opacity', 0.25))
        filter_complex_parts.append(f"[{input_map['effect']}:v]scale={W}:{H},format=rgba[effect_scaled]")
        filter_complex_parts.append(
            f"{last_video_stream}[effect_scaled]"
            f"blend=all_mode={blend_mode}:all_opacity={effect_opacity}[v_effect]"
        )
        last_video_stream = "[v_effect]"

    if 'presenter' in input_map:
        pos = params.get('presenter_position', 'Inferior Central')
        pos_x = {'Inferior Esquerdo': '10', 'Inferior Central': '(W-w)/2', 'Inferior Direito': 'W-w-10'}.get(pos, '(W-w)/2')
        scale = float(params.get('presenter_scale', 0.40))
        target_h = int(H * scale)
        position = f"{pos_x}:H-h"

        if params.get('presenter_chroma_enabled'):
            chroma_hex = params.get('presenter_chroma_color', '#00FF00').replace('#', '0x')
            raw_sim = float(params.get('presenter_chroma_similarity', 0.20))
            raw_smth = float(params.get('presenter_chroma_blend', 0.10))
            raw_sim = max(0.0, min(raw_sim, 1.0))
            raw_smth = max(0.0, min(raw_smth, 1.0))
            sim = 0.05 + 0.45 * raw_sim
            smth = 0.02 + 0.28 * raw_smth
            filter_complex_parts.append(
                f"[{input_map['presenter']}:v]"
                f"scale=w=-1:h={target_h},format=rgba,chromakey={chroma_hex}:{sim}:{smth}"
                f"[presenter_keyed]"
            )
            filter_complex_parts.append(f"{last_video_stream}[presenter_keyed]overlay={position}:format=auto[v_presenter]")
        else:
            filter_complex_parts.append(f"[{input_map['presenter']}:v]scale=w=-1:h={target_h}[presenter_scaled]")
            filter_complex_parts.append(f"{last_video_stream}[presenter_scaled]overlay={position}:format=auto[v_presenter]")

        last_video_stream = "[v_presenter]"

    if 'png' in input_map:
        pos_map = {
            "Superior Esquerdo": "10:10",
            "Superior Direito": "W-w-10:10",
            "Inferior Esquerdo": "10:H-h-10",
            "Inferior Direito": "W-w-10:H-h-10",
        }
        position = pos_map.get(params.get('png_overlay_position'), "W-w-10:H-h-10")
        scale = params.get('png_overlay_scale', 0.15)
        opacity = params.get('png_overlay_opacity', 1.0)
        filter_complex_parts.append(f"[{input_map['png']}:v]format=rgba,colorchannelmixer=aa={opacity},scale=w='iw*{scale}':h=-1[png_scaled]")
        filter_complex_parts.append(f"{last_video_stream}[png_scaled]overlay={position}:format=auto[v_png]")
        last_video_stream = "[v_png]"

    if params.get('add_fade_out'):
        fade_duration = max(0.0, float(params.get('fade_out_duration', 10)))
        fade_start_time = narration_duration if narration_duration > 0 else max(0.0, content_duration - fade_duration)
        progress_queue.put((
            "status",
            f"[{log_prefix}] Fade-out configurado para iniciar em {fade_start_time:.2f}s após narração de {narration_duration:.2f}s; vídeo visível até {total_duration:.2f}s.",
            "info",
        ))
        filter_complex_parts.append(f"{last_video_stream}fade=t=out:st={fade_start_time}:d={fade_duration}:c=black[v_fadeout]")
        last_video_stream = "[v_fadeout]"

    styled_subtitle_path = _create_styled_ass_from_srt(subtitle_path, params['subtitle_style'], temp_dir, (W, H))
    if styled_subtitle_path and os.path.isfile(styled_subtitle_path):
        escaped_sub_path = _escape_ffmpeg_path(styled_subtitle_path)
        font_file_path = params.get('subtitle_style', {}).get('font_file')

        subtitle_filter = f"subtitles=filename='{escaped_sub_path}'"
        if font_file_path and os.path.isfile(font_file_path):
            font_dir = Path(font_file_path).parent
            escaped_font_dir = _escape_ffmpeg_path(str(font_dir.resolve()))
            subtitle_filter += f":fontsdir='{escaped_font_dir}'"

        filter_complex_parts.append(f"{last_video_stream}{subtitle_filter}[v_subs]")
        last_video_stream = "[v_subs]"

    progress_queue.put(("status", f"[{log_prefix}] Construindo filtros de áudio...", "info"))
    last_audio_stream: Optional[str] = None
    if 'narration' in input_map and 'music' in input_map:
        filter_complex_parts.append(f"[{input_map['narration']}:a]volume={params['narration_volume']}dB[narr_vol]")
        filter_complex_parts.append(f"[{input_map['music']}:a]volume={params['music_volume']}dB[music_vol]")
        filter_complex_parts.append(f"[narr_vol]asplit=2[narr_main][narr_side]")
        filter_complex_parts.append(f"[music_vol][narr_side]sidechaincompress=release=250[music_ducked]")
        filter_complex_parts.append(f"[narr_main][music_ducked]amix=inputs=2:duration=longest:dropout_transition=3[a_mix]")
        last_audio_stream = "[a_mix]"
    elif 'narration' in input_map:
        filter_complex_parts.append(f"[{input_map['narration']}:a]volume={params['narration_volume']}dB[aout]")
        last_audio_stream = "[aout]"
    elif 'music' in input_map:
        filter_complex_parts.append(f"[{input_map['music']}:a]volume={params['music_volume']}dB[aout]")
        last_audio_stream = "[aout]"

    if params.get('add_fade_out') and last_audio_stream:
        fade_duration = max(0.0, float(params.get('fade_out_duration', 10)))
        fade_start_time = narration_duration if narration_duration > 0 else max(0.0, content_duration - fade_duration)
        filter_complex_parts.append(f"{last_audio_stream}afade=t=out:st={fade_start_time}:d={fade_duration}[a_fadeout]")
        last_audio_stream = "[a_fadeout]"

    final_output_path = str(Path(params['output_folder']) / params['output_filename_single'])
    content_only_output_path = final_output_path
    if intro_info:
        content_only_output_path = os.path.join(
            temp_dir,
            f"main-content-{Path(params['output_filename_single']).stem}.mp4",
        )

    cmd_prefix = [params['ffmpeg_path'], '-y', *inputs]

    filter_complex_parts.append(f"{last_video_stream}format=yuv420p[vout]")
    map_args.extend(["-map", "[vout]"])

    if last_audio_stream:
        map_args.extend(["-map", last_audio_stream])
    elif 'main_video' in input_map:
        map_args.extend(["-map", f"{input_map['main_video']}:a?"])

    final_filter_str = ""
    if filter_complex_parts:
        final_filter_str = ";".join(filter_complex_parts)
        logger.debug(f"[{log_prefix}] Cadeia de Filtros Completa:\n{final_filter_str}")
        cmd_prefix.extend(['-filter_complex', final_filter_str])

    cmd_prefix.extend(map_args)

    force_reencode = any(s in final_filter_str for s in ['scale=', 'blend=', 'overlay=', 'fade=', 'subtitles='])
    primary_codec_params = _get_codec_params(params, force_reencode)

    audio_args = ['-c:a', 'aac', '-b:a', '192k'] if last_audio_stream else ['-c:a', 'copy']

    time_args: List[str] = []
    if total_duration > 0:
        time_args.extend(["-t", f"{total_duration:.6f}"])
    time_args.append("-shortest")

    output_args = ['-movflags', '+faststart', content_only_output_path]

    def build_cmd(codec_params: List[str]) -> List[str]:
        return [*cmd_prefix, *codec_params, *audio_args, *time_args, *output_args]

    codec_attempts: List[Tuple[str, List[str]]] = []

    def codec_label(codec_params: List[str]) -> str:
        if any(enc in codec_params for enc in ('h264_nvenc', 'hevc_nvenc')):
            return 'GPU (NVENC)'
        if any(enc in codec_params for enc in ('libx264', 'libx265')):
            return 'CPU (libx264)'
        if 'copy' in codec_params:
            return 'Cópia direta'
        return 'Encoder padrão'

    codec_attempts.append((codec_label(primary_codec_params), primary_codec_params))

    if force_reencode and any(enc in primary_codec_params for enc in ('h264_nvenc', 'hevc_nvenc')):
        cpu_params = params.copy()
        cpu_params['video_codec'] = 'CPU (libx264)'
        fallback_codec_params = _get_codec_params(cpu_params, True)
        codec_attempts.append((codec_label(fallback_codec_params), fallback_codec_params))

    def final_progress_callback(pct: float) -> None:
        progress_queue.put(("progress", pct))

    success = False
    total_attempts = len(codec_attempts)
    for attempt_idx, (label, codec_params) in enumerate(codec_attempts, start=1):
        if attempt_idx > 1:
            progress_queue.put((
                "status",
                f"[{log_prefix}] Tentando novamente com {label} (tentativa {attempt_idx}/{total_attempts})...",
                "warning",
            ))
            progress_queue.put(("progress", 0.0))

        cmd_final_attempt = build_cmd(codec_params)
        success = _execute_ffmpeg(
            cmd_final_attempt,
            total_duration,
            final_progress_callback,
            cancel_event,
            f"{log_prefix} (Final - {label})",
            progress_queue,
        )

        if success or cancel_event.is_set():
            break

        if attempt_idx < total_attempts:
            progress_queue.put((
                "status",
                f"[{log_prefix}] Falha ao renderizar com {label}. Alternando encoder...",
                "warning",
            ))

    if not success:
        return False

    if not intro_info:
        return True

    combined = _combine_intro_with_main(intro_info, content_only_output_path, final_output_path, params, progress_queue, cancel_event, log_prefix)
    if combined and content_only_output_path != final_output_path and os.path.exists(content_only_output_path):
        try:
            os.remove(content_only_output_path)
        except OSError:
            pass
    return combined
