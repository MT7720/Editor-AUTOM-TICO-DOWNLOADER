"""Funções auxiliares para criação de introduções com animação de digitação."""

from __future__ import annotations

import math
import os
import tempfile
import threading
import wave
from array import array
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from .ffmpeg_pipeline import execute_ffmpeg
from shared import INTRO_FONT_REGISTRY, get_intro_font_candidates, resolve_intro_font_candidate_path

__all__ = [
    "wrap_text_to_width",
    "generate_typing_audio",
    "create_typing_intro_clip",
]


def wrap_text_to_width(text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    if max_width <= 0:
        return [text]

    dummy_img = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(dummy_img)
    lines: List[str] = []
    paragraphs = text.split("\n") if text else [""]

    for paragraph in paragraphs:
        paragraph = paragraph or ""
        words = paragraph.split(" ")
        current_line = ""

        for raw_word in words:
            word = raw_word.strip()
            if not word:
                if current_line:
                    lines.append(current_line)
                    current_line = ""
                continue

            tentative = word if not current_line else f"{current_line} {word}"
            if draw.textlength(tentative, font=font) <= max_width:
                current_line = tentative
                continue

            if current_line:
                lines.append(current_line)
                current_line = ""

            if draw.textlength(word, font=font) <= max_width:
                current_line = word
                continue

            chunk = ""
            for char in word:
                candidate = f"{chunk}{char}"
                if draw.textlength(candidate, font=font) <= max_width or not chunk:
                    chunk = candidate
                else:
                    lines.append(chunk)
                    chunk = char
            current_line = chunk

        if current_line:
            lines.append(current_line)

        lines.append("")

    if lines and lines[-1] == "":
        lines.pop()

    return lines or [""]


def generate_typing_audio(
    text: str,
    char_duration: float,
    hold_duration: float,
    output_path: str,
    sample_rate: int = 44100,
) -> float:
    amplitude = 0.35
    base_frequency = 1100.0
    tone_ratio = 0.65
    data = array("h")

    for char in text:
        total_samples = max(1, int(round(char_duration * sample_rate)))
        tone_samples = 0
        if not char.isspace():
            tone_samples = max(1, int(round(total_samples * tone_ratio)))
            tone_samples = min(tone_samples, total_samples)

        for n in range(tone_samples):
            env = math.sin(math.pi * (n / max(1, tone_samples)))
            sample = int(env * amplitude * 32767 * math.sin(2 * math.pi * base_frequency * (n / sample_rate)))
            data.append(sample)

        silence_samples = total_samples - tone_samples
        if silence_samples > 0:
            data.extend([0] * silence_samples)

    hold_samples = max(0, int(round(hold_duration * sample_rate)))
    if hold_samples:
        data.extend([0] * hold_samples)

    with wave.open(output_path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(data.tobytes())

    return len(data) / float(sample_rate)


def create_typing_intro_clip(
    text: str,
    resolution: Tuple[int, int],
    params: Dict[str, any],
    temp_dir: str,
    progress_queue,
    cancel_event: threading.Event,
    log_prefix: str,
) -> Optional[Dict[str, any]]:
    if cancel_event.is_set():
        return None

    width, height = resolution
    frame_rate = 30
    base_char_duration = 0.08
    frames_per_char = max(2, int(round(frame_rate * base_char_duration)))
    char_duration = frames_per_char / frame_rate
    hold_frames = max(frame_rate, int(round(frame_rate * 1.5)))
    hold_duration = hold_frames / frame_rate

    intro_temp_dir = tempfile.mkdtemp(prefix="intro-clip-", dir=temp_dir)
    frames_dir = os.path.join(intro_temp_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    font_size = max(36, int(height * 0.08))
    intro_font_choice = str(params.get("intro_font_choice") or "")
    intro_font_bold = bool(params.get("intro_font_bold"))

    subtitle_style = params.get("subtitle_style") or {}
    subtitle_font_path = subtitle_style.get("font_file") if isinstance(subtitle_style, dict) else None

    preferred_candidates: List[str] = []
    preferred_candidates.extend(get_intro_font_candidates(intro_font_choice, bold=intro_font_bold))
    if intro_font_bold:
        preferred_candidates.extend(get_intro_font_candidates(intro_font_choice, bold=False))
    if subtitle_font_path:
        preferred_candidates.append(str(subtitle_font_path))
    preferred_candidates.extend(["DejaVuSans.ttf", "arial.ttf", "LiberationSans-Regular.ttf"])

    deduped_candidates: List[str] = []
    seen_candidates = set()
    for candidate in preferred_candidates:
        if not candidate:
            continue
        marker = candidate.lower()
        if marker in seen_candidates:
            continue
        seen_candidates.add(marker)
        deduped_candidates.append(candidate)

    font: ImageFont.ImageFont
    used_candidate_marker: Optional[str] = None
    for candidate in deduped_candidates:
        try:
            font = ImageFont.truetype(candidate, font_size)
            used_candidate_marker = candidate.lower()
            break
        except (OSError, FileNotFoundError):
            continue
    else:
        font = ImageFont.load_default()

    bold_markers = set()
    registry_entry = INTRO_FONT_REGISTRY.get(intro_font_choice or "")
    if registry_entry:
        for raw_candidate in registry_entry.get("bold", []):
            resolved = resolve_intro_font_candidate_path(str(raw_candidate))
            bold_markers.add(str(raw_candidate).lower())
            bold_markers.add(resolved.lower())

    bold_font_loaded = bool(used_candidate_marker and used_candidate_marker in bold_markers)
    simulate_bold = bool(intro_font_bold and not bold_font_loaded)
    stroke_width = 2 if simulate_bold else 0

    max_text_width = int(width * 0.8)

    def render_frame_text(current_text: str) -> Image.Image:
        img = Image.new("RGB", (width, height), color=(0, 0, 0))
        draw = ImageDraw.Draw(img)
        lines = wrap_text_to_width(current_text, font, max_text_width)
        line_heights: List[int] = []
        for line in lines:
            bbox = draw.textbbox((0, 0), line or " ", font=font, stroke_width=stroke_width)
            line_heights.append(bbox[3] - bbox[1])

        line_gap = max(10, int(font_size * 0.3))
        total_text_height = sum(line_heights) + line_gap * (len(line_heights) - 1 if line_heights else 0)
        start_y = max(0, (height - total_text_height) // 2)

        y_cursor = start_y
        for idx, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line or " ", font=font, stroke_width=stroke_width)
            line_width = bbox[2] - bbox[0]
            x_cursor = max(0, (width - line_width) // 2)
            if line:
                draw.text(
                    (x_cursor, y_cursor),
                    line,
                    font=font,
                    fill=(255, 255, 255),
                    stroke_width=stroke_width,
                    stroke_fill=(255, 255, 255),
                )
            y_cursor += line_heights[idx] + line_gap

        return img

    frame_index = 0
    current_text = ""
    for char in text:
        if cancel_event.is_set():
            return None
        current_text += char
        frame_image = render_frame_text(current_text)
        for _ in range(frames_per_char):
            frame_path = os.path.join(frames_dir, f"frame_{frame_index:05d}.png")
            frame_image.save(frame_path)
            frame_index += 1

    if frame_index == 0:
        frame_image = render_frame_text(text)
        frame_path = os.path.join(frames_dir, "frame_00000.png")
        frame_image.save(frame_path)
        frame_index = 1

    final_image = render_frame_text(text)
    for _ in range(hold_frames):
        frame_path = os.path.join(frames_dir, f"frame_{frame_index:05d}.png")
        final_image.save(frame_path)
        frame_index += 1

    total_frames = frame_index
    total_duration = total_frames / frame_rate

    audio_path = os.path.join(intro_temp_dir, "typing_audio.wav")
    generate_typing_audio(text, char_duration, hold_duration, audio_path)

    intro_clip_path = os.path.join(intro_temp_dir, "typing_intro.mp4")
    frame_pattern = os.path.join(frames_dir, "frame_%05d.png")

    progress_queue.put(("status", f"[{log_prefix}] Gerando clipe de introdução digitada...", "info"))

    cmd_intro = [
        params["ffmpeg_path"], "-y",
        "-framerate", str(frame_rate),
        "-i", frame_pattern,
        "-i", audio_path,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", intro_clip_path,
    ]

    if not execute_ffmpeg(cmd_intro, total_duration, None, cancel_event, f"{log_prefix} (Intro)", progress_queue):
        return None

    return {
        "path": intro_clip_path,
        "duration": total_duration,
    }
