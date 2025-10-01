"""Utility helpers shared across the video processing pipeline."""

from __future__ import annotations

import math
import os
import random
import re
from itertools import islice
from pathlib import Path
from queue import Queue
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import threading

from .shared import (
    _execute_ffmpeg,
    _probe_media_properties,
    logger,
)

__all__ = [
    "_parse_resolution",
    "_build_subtitle_style_string",
    "_create_styled_ass_from_srt",
    "_create_concatenated_audio",
    "_get_music_playlist",
    "_process_images_in_chunks",
]

_DEFAULT_RESOLUTION = (1920, 1080)


def _parse_resolution(resolution: str) -> Tuple[int, int]:
    """Extrai uma resolução ``(width, height)`` de uma string da interface."""

    if not resolution:
        return _DEFAULT_RESOLUTION

    match = re.search(r"(\d{3,5})\s*[xX]\s*(\d{3,5})", resolution)
    if match:
        width, height = int(match.group(1)), int(match.group(2))
        if width > 0 and height > 0:
            return width, height

    match = re.search(r"(\d{3,4})p", resolution, re.IGNORECASE)
    if match:
        height = int(match.group(1))
        if height > 0:
            width = int(round(height * 16 / 9))
            return width, height

    return _DEFAULT_RESOLUTION


def _build_subtitle_style_string(style_params: Dict) -> str:
    """Constrói a string usada pelo ``force_style`` do FFmpeg."""

    font_name = Path(style_params.get('font_file', '')).stem or 'Arial'

    def to_ass_color(hex_color: str) -> str:
        hex_color = (hex_color or '#FFFFFF').lstrip('#')
        if len(hex_color) == 3:
            hex_color = ''.join(ch * 2 for ch in hex_color)
        if len(hex_color) != 6:
            hex_color = 'FFFFFF'
        return f"&H{hex_color[4:6]}{hex_color[2:4]}{hex_color[0:2]}".upper()

    fontsize = int(style_params.get('fontsize', 28))
    style_parts = {
        'FontName': font_name,
        'FontSize': fontsize,
        'PrimaryColour': to_ass_color(style_params.get('text_color', '#FFFFFF')),
        'OutlineColour': to_ass_color(style_params.get('outline_color', '#000000')),
        'BorderStyle': 1,
        'Outline': style_params.get('outline', 2),
        'Shadow': style_params.get('shadow', 1),
        'Bold': -1 if style_params.get('bold', True) else 0,
        'Italic': -1 if style_params.get('italic', False) else 0,
        'Alignment': style_params.get('position_map', {}).get(style_params.get('position'), 2),
        'MarginV': int(fontsize * 0.7),
    }
    return ",".join(f"{key}={value}" for key, value in style_parts.items())


def _create_styled_ass_from_srt(
    subtitle_path: Optional[str],
    style_params: Optional[Dict],
    temp_dir: str,
    resolution: Tuple[int, int],
) -> Optional[str]:
    """Converte um arquivo ``.srt`` para ``.ass`` aplicando o estilo configurado."""

    if not subtitle_path or not os.path.isfile(subtitle_path):
        return None

    style_params = style_params or {}
    style_name = "Default"
    output_path = os.path.join(temp_dir, f"styled_{Path(subtitle_path).stem}.ass")

    def hex_to_ass(hex_color: str, alpha: int = 0) -> str:
        hex_color = (hex_color or '#FFFFFF').lstrip('#')
        if len(hex_color) == 3:
            hex_color = ''.join(ch * 2 for ch in hex_color)
        if len(hex_color) != 6:
            hex_color = 'FFFFFF'
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"

    fontsize = int(style_params.get('fontsize', 28))
    margin_v = int(fontsize * 0.7)
    margin_lr = int(fontsize * 0.6)

    style_line = ",".join(
        [
            style_name,
            Path(style_params.get('font_file', '')).stem or 'Arial',
            str(fontsize),
            hex_to_ass(style_params.get('text_color', '#FFFFFF'), 0),
            hex_to_ass(style_params.get('secondary_color', '#FFFFFF'), 0),
            hex_to_ass(style_params.get('outline_color', '#000000'), 0),
            hex_to_ass(style_params.get('back_color', '#000000'), 255),
            "-1" if style_params.get('bold', True) else "0",
            "-1" if style_params.get('italic', False) else "0",
            "0",
            "0",
            "100",
            "100",
            "0",
            "0",
            str(style_params.get('border_style', 1)),
            str(style_params.get('outline', 2)),
            str(style_params.get('shadow', 1)),
            str(style_params.get('position_map', {}).get(style_params.get('position'), 2)),
            str(margin_lr),
            str(margin_lr),
            str(margin_v),
            "1",
        ]
    )

    def parse_srt_entries() -> Iterable[Tuple[str, str, str]]:
        with open(subtitle_path, 'r', encoding='utf-8-sig') as src:
            content = src.read().replace('\r', '')
        blocks = re.split(r"\n\s*\n", content.strip())
        time_pattern = re.compile(r"(\d{1,2}):(\d{2}):(\d{2}),(\d{3})\s+-->\s+(\d{1,2}):(\d{2}):(\d{2}),(\d{3})")
        for block in blocks:
            lines = [line.strip('\ufeff') for line in block.splitlines() if line.strip()]
            if len(lines) < 2:
                continue
            time_match = time_pattern.match(lines[1]) if not time_pattern.match(lines[0]) else time_pattern.match(lines[0])
            text_lines = lines[2:] if time_pattern.match(lines[1]) else lines[1:]
            if not time_match or not text_lines:
                continue
            sh, sm, ss, sms, eh, em, es, ems = map(int, time_match.groups())
            start = f"{sh:d}:{sm:02d}:{ss:02d}.{sms // 10:02d}"
            end = f"{eh:d}:{em:02d}:{es:02d}.{ems // 10:02d}"
            text = "\\N".join(text_lines)
            yield start, end, text

    width, height = resolution
    header = [
        "[Script Info]",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: {style_line}",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    events: List[str] = []
    for start, end, text in parse_srt_entries():
        events.append(f"Dialogue: 0,{start},{end},{style_name},,0000,0000,0000,,{text}")

    if not events:
        return subtitle_path

    os.makedirs(temp_dir, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as ass_file:
        ass_file.write("\n".join(header + events))

    logger.info("[_create_styled_ass_from_srt] Arquivo SRT '%s' convertido para ASS estilizado em '%s'", subtitle_path, output_path)
    return output_path


def _create_concatenated_audio(
    playlist: Sequence[str],
    output_path: str,
    temp_dir: str,
    params: Dict[str, Any],
    cancel_event: threading.Event,
    progress_queue: Queue,
    log_prefix: str,
) -> bool:
    if not playlist:
        return False

    concat_file = os.path.join(temp_dir, 'music_concat.txt')
    os.makedirs(temp_dir, exist_ok=True)
    with open(concat_file, 'w', encoding='utf-8') as fp:
        for track in playlist:
            fp.write(f"file '{Path(track).as_posix()}'\n")

    total_duration = 0.0
    for track in playlist:
        props = _probe_media_properties(track, params['ffmpeg_path'])
        if props and props.get('format', {}).get('duration'):
            total_duration += float(props['format']['duration'])

    codec_args: List[str]
    output_suffix = Path(output_path).suffix.lower()

    forced_codec = params.get('music_concat_codec')
    forced_bitrate = params.get('music_concat_bitrate', '192k')

    if forced_codec:
        codec_args = ['-c:a', forced_codec]
        if forced_codec != 'copy':
            codec_args += ['-b:a', str(forced_bitrate)]
    elif output_suffix in {'.m4a', '.mp4', '.m4v', '.mov', '.mkv'}:
        codec_args = ['-c:a', 'aac', '-b:a', str(forced_bitrate)]
    else:
        codec_args = ['-c', 'copy']

    cmd = [
        params['ffmpeg_path'], '-y',
        '-f', 'concat', '-safe', '0',
        '-i', concat_file,
        *codec_args,
        output_path,
    ]

    progress_queue.put(("status", f"[{log_prefix}] Concatenando {len(playlist)} músicas de fundo...", "info"))
    return _execute_ffmpeg(
        cmd,
        max(total_duration, 1.0),
        None,
        cancel_event,
        f"{log_prefix} (Concat Música)",
        progress_queue,
    )


def _get_music_playlist(available_music: List[str], target_duration: float, params: Dict, ffmpeg_path: str) -> List[str]:
    """Cria uma lista de caminhos de música para atingir a duração desejada."""
    if not available_music:
        return []

    if params.get('batch_music_behavior') == 'loop':
        return [random.choice(available_music)]

    playlist: List[str] = []
    current_duration = 0.0
    shuffled_music = random.sample(available_music, len(available_music))

    while current_duration < target_duration and target_duration > 0:
        if not shuffled_music:
            shuffled_music = random.sample(available_music, len(available_music))
        music_path = shuffled_music.pop(0)
        props = _probe_media_properties(music_path, ffmpeg_path)
        if props and props.get('format', {}).get('duration'):
            duration = float(props['format']['duration'])
            playlist.append(music_path)
            current_duration += duration

    if not playlist and available_music:
        playlist.append(random.choice(available_music))

    return playlist


def _process_images_in_chunks(
    params: Dict[str, Any],
    images: Sequence[Path],
    final_duration: float,
    temp_dir: str,
    progress_queue: Queue,
    cancel_event: threading.Event,
    log_prefix: str,
) -> Tuple[str, bool]:
    if not images:
        progress_queue.put(("status", f"[{log_prefix}] Nenhuma imagem disponível para o slideshow.", "error"))
        return "", False

    ffmpeg_path = params['ffmpeg_path']
    width, height = _parse_resolution(params.get('resolution', ''))
    image_duration = max(0.1, float(params.get('image_duration', 5)))

    if final_duration > 0:
        slide_count = max(1, int(math.ceil(final_duration / image_duration)))
    else:
        slide_count = len(images)

    def cycle_images(seq: Sequence[Path]) -> Iterable[Path]:
        while True:
            for item in seq:
                yield item

    selected_images = list(islice(cycle_images(images), slide_count))

    os.makedirs(temp_dir, exist_ok=True)
    list_file = os.path.join(temp_dir, 'slideshow_images.txt')
    with open(list_file, 'w', encoding='utf-8') as fp:
        for idx, image_path in enumerate(selected_images):
            posix = Path(image_path).as_posix()
            fp.write(f"file '{posix}'\n")
            fp.write(f"duration {image_duration:.3f}\n")
        # repetir a última imagem para garantir a duração correta
        fp.write(f"file '{Path(selected_images[-1]).as_posix()}'\n")

    output_path = os.path.join(temp_dir, 'slideshow.mp4')
    vf_filters = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )
    fps = float(params.get('slideshow_fps') or params.get('output_fps') or 30)
    cmd = [
        ffmpeg_path, '-y',
        '-f', 'concat', '-safe', '0',
        '-i', list_file,
        '-vf', vf_filters,
        '-r', f"{fps}",
        '-pix_fmt', 'yuv420p',
        '-c:v', params.get('slideshow_video_codec', 'libx264'),
        '-preset', params.get('slideshow_preset', 'veryfast'),
        '-crf', str(params.get('slideshow_crf', 20)),
        output_path,
    ]

    total_duration = image_duration * len(selected_images)
    progress_queue.put(("status", f"[{log_prefix}] Renderizando slideshow com {len(selected_images)} imagens...", "info"))
    success = _execute_ffmpeg(
        cmd,
        max(total_duration, 1.0),
        None,
        cancel_event,
        f"{log_prefix} (Slideshow)",
        progress_queue,
    )

    return output_path, success
