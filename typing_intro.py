"""Utilities to build typing intro clips with per-language text."""
from __future__ import annotations

import math
import os
import subprocess
import tempfile
import unicodedata
import wave
from array import array
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

LANGUAGE_CODE_MAP: Dict[str, str] = {
    "PT": "Português",
    "ING": "Inglês",
    "ESP": "Espanhol",
    "FRAN": "Francês",
    "BUL": "Búlgaro",
    "ROM": "Romeno",
    "ALE": "Alemão",
    "GREGO": "Grego",
    "ITA": "Italiano",
    "POL": "Polonês",
    "HOLAND": "Holandês",
}

LANGUAGE_ALIASES: Dict[str, str] = {
    "EN": "ING",
    "ENGLISH": "ING",
    "INGLES": "ING",
    "INGLÊS": "ING",
    "ES": "ESP",
    "ESPANHOL": "ESP",
    "ESPAÑOL": "ESP",
    "FR": "FRAN",
    "FRANCES": "FRAN",
    "FRANCÊS": "FRAN",
    "FRANCAIS": "FRAN",
    "DE": "ALE",
    "GERMAN": "ALE",
    "GERMANO": "ALE",
    "ALEMAO": "ALE",
    "ALEMÃO": "ALE",
    "IT": "ITA",
    "ITALIANO": "ITA",
    "RO": "ROM",
    "ROMENO": "ROM",
    "BG": "BUL",
    "BULGARO": "BUL",
    "BÚLGARO": "BUL",
    "NL": "HOLAND",
    "HOLANDES": "HOLAND",
    "HOLANDÊS": "HOLAND",
    "PL": "POL",
    "POLONES": "POL",
    "POLONÊS": "POL",
    "EL": "GREGO",
    "GR": "GREGO",
    "GREGO": "GREGO",
}


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize('NFKD', value or '')
    return ''.join(ch for ch in normalized if not unicodedata.combining(ch))


LANGUAGE_NAME_TO_CODE: Dict[str, str] = {
    _strip_accents(name).upper(): code for code, name in LANGUAGE_CODE_MAP.items()
}


def normalize_language_code(raw_code: Optional[str]) -> Optional[str]:
    if not raw_code:
        return None
    candidate = _strip_accents(str(raw_code).strip()).upper()
    if not candidate:
        return None
    if candidate in LANGUAGE_ALIASES:
        candidate = LANGUAGE_ALIASES[candidate]
    if candidate in LANGUAGE_CODE_MAP:
        return candidate
    if candidate in LANGUAGE_NAME_TO_CODE:
        return LANGUAGE_NAME_TO_CODE[candidate]
    return None


def infer_language_code_from_filename(filename: str) -> Optional[str]:
    if not filename:
        return None
    stem = Path(filename).stem
    tokens = stem.replace('-', ' ').replace('.', ' ').split()
    for token in reversed(tokens):
        normalized = normalize_language_code(token)
        if normalized:
            return normalized
    return None


def wrap_text_to_width(text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    if not text:
        return [""]

    drawing = ImageDraw.Draw(Image.new('RGB', (1, 1), color=(0, 0, 0)))
    lines: list[str] = []

    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue

        current_line = words[0]
        for word in words[1:]:
            candidate = f"{current_line} {word}" if current_line else word
            if drawing.textlength(candidate, font=font) <= max_width:
                current_line = candidate
            else:
                if current_line:
                    lines.append(current_line)
                if drawing.textlength(word, font=font) <= max_width:
                    current_line = word
                else:
                    split_word = ""
                    for char in word:
                        tentative = split_word + char
                        if drawing.textlength(tentative, font=font) > max_width and split_word:
                            lines.append(split_word)
                            split_word = char
                        else:
                            split_word = tentative
                    current_line = split_word
        lines.append(current_line)

    return lines if lines else [""]


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
    data = array('h')

    for char in text or "":
        total_samples = max(1, int(round(char_duration * sample_rate)))
        tone_samples = 0
        if not char.isspace():
            tone_samples = max(1, int(round(total_samples * tone_ratio)))
            tone_samples = min(tone_samples, total_samples)

        for n in range(tone_samples):
            envelope = math.sin(math.pi * (n / max(1, tone_samples)))
            sample = int(
                envelope
                * amplitude
                * 32767
                * math.sin(2 * math.pi * base_frequency * (n / sample_rate))
            )
            data.append(sample)

        silence_samples = total_samples - tone_samples
        if silence_samples > 0:
            data.extend([0] * silence_samples)

    hold_samples = max(0, int(round(hold_duration * sample_rate)))
    if hold_samples:
        data.extend([0] * hold_samples)

    with wave.open(output_path, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(data.tobytes())

    return len(data) / float(sample_rate)


def _load_font(font_candidates: list[str], font_size: int) -> ImageFont.ImageFont:
    for candidate in font_candidates:
        if not candidate:
            continue
        try:
            return ImageFont.truetype(candidate, font_size)
        except (OSError, FileNotFoundError):
            continue
    return ImageFont.load_default()


def create_typing_intro_clip(
    text: str,
    resolution: Tuple[int, int],
    subtitle_style: Optional[Dict[str, Any]],
    temp_dir: str,
    ffmpeg_path: str,
) -> Dict[str, Any]:
    width, height = resolution
    frame_rate = 30
    base_char_duration = 0.08
    frames_per_char = max(2, int(round(frame_rate * base_char_duration)))
    char_duration = frames_per_char / frame_rate
    hold_frames = max(frame_rate, int(round(frame_rate * 1.2)))
    hold_duration = hold_frames / frame_rate

    intro_temp_dir = tempfile.mkdtemp(prefix="typing-intro-", dir=temp_dir)
    frames_dir = os.path.join(intro_temp_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    font_size = max(36, int(height * 0.08))
    font_candidates: list[str] = []
    if subtitle_style and isinstance(subtitle_style, dict):
        subtitle_font_path = subtitle_style.get('font_file')
        if subtitle_font_path:
            font_candidates.append(subtitle_font_path)
    font_candidates.extend(["arial.ttf", "DejaVuSans.ttf"])

    font = _load_font(font_candidates, font_size)
    max_text_width = int(width * 0.8)

    def render_frame(current_text: str) -> Image.Image:
        img = Image.new('RGB', (width, height), color=(0, 0, 0))
        draw = ImageDraw.Draw(img)
        lines = wrap_text_to_width(current_text, font, max_text_width)
        if not lines:
            lines = [""]

        line_heights: list[int] = []
        for line in lines:
            bbox = draw.textbbox((0, 0), line or ' ', font=font)
            line_heights.append(bbox[3] - bbox[1])

        line_gap = max(10, int(font_size * 0.3))
        total_text_height = sum(line_heights) + line_gap * (len(line_heights) - 1 if line_heights else 0)
        start_y = max(0, (height - total_text_height) // 2)
        y_cursor = start_y

        for idx, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line or ' ', font=font)
            line_width = bbox[2] - bbox[0]
            x = max(0, (width - line_width) // 2)
            draw.text((x, y_cursor), line, font=font, fill=(255, 255, 255))
            y_cursor += line_heights[idx] + line_gap

        return img

    current_text = ""
    frame_index = 0
    for char in text:
        current_text += char
        for _ in range(frames_per_char):
            frame_path = os.path.join(frames_dir, f"frame_{frame_index:05d}.png")
            render_frame(current_text).save(frame_path)
            frame_index += 1

    for _ in range(hold_frames):
        frame_path = os.path.join(frames_dir, f"frame_{frame_index:05d}.png")
        render_frame(current_text).save(frame_path)
        frame_index += 1

    video_path = os.path.join(intro_temp_dir, "intro.mp4")
    audio_path = os.path.join(intro_temp_dir, "intro.wav")

    duration = generate_typing_audio(text, char_duration, hold_duration, audio_path)

    ffmpeg_cmd = [
        ffmpeg_path,
        '-y',
        '-framerate', str(frame_rate),
        '-i', os.path.join(frames_dir, 'frame_%05d.png'),
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
        video_path,
    ]
    subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return {
        'directory': intro_temp_dir,
        'video_path': video_path,
        'audio_path': audio_path,
        'duration': duration,
        'fade_duration': min(0.75, max(0.4, duration * 0.2)),
    }


def resolve_intro_text(intro_params: Dict[str, Any], language_code: Optional[str]) -> Optional[str]:
    if not intro_params.get('intro_enabled'):
        return None

    intro_texts = intro_params.get('intro_texts') or {}
    default_text = (intro_params.get('intro_default_text') or '').strip()

    if language_code:
        direct_text = (intro_texts.get(language_code) or '').strip()
        if direct_text:
            return direct_text

    return default_text or None
