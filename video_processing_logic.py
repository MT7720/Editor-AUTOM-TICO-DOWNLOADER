import subprocess
import tempfile
import platform
import os
import re
import math
import textwrap
import glob
import shutil
import json
import logging
import time
import atexit
import threading
import random
import locale
import gc
import sys
import requests

import unicodedata
import wave
from array import array
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional, Callable, IO
from queue import Queue, Empty
from math import ceil
from PIL import Image, ImageFile, ImageDraw, ImageFont

try:
    from deep_translator import GoogleTranslator  # type: ignore
except Exception:  # pragma: no cover - biblioteca externa opcional
    GoogleTranslator = None

# --- Configuração ---
logger = logging.getLogger(__name__)
ImageFile.LOAD_TRUNCATED_IMAGES = True # Permite carregar imagens truncadas

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
    "RUS": "Russo",
    "UKR": "Ucraniano",
    "CHEC": "Tcheco",
    "SLO": "Eslovaco",
    "HUN": "Húngaro",
    "SER": "Sérvio",
    "CRO": "Croata",
    "SUE": "Sueco",
    "DAN": "Dinamarquês",
    "NOR": "Norueguês",
    "FIN": "Finlandês",
    "ISL": "Islandês",
    "TUR": "Turco",
    "ARA": "Árabe",
    "HIN": "Hindi",
    "BEN": "Bengali",
    "JAP": "Japonês",
    "KOR": "Coreano",
    "CHI": "Chinês (Simplificado)",
    "THA": "Tailandês",
    "VIE": "Vietnamita",
    "MAL": "Malaio",
    "IND": "Indonésio",
    "FIL": "Filipino",
    "PER": "Persa",
    "HEB": "Hebraico",
    "SWA": "Suaíli",
    "AFR": "Africâner",
    "CAT": "Catalão",
    "GALE": "Galego",
}

LANGUAGE_ALIASES: Dict[str, str] = {
    "PT-BR": "PT",
    "PT-PT": "PT",
    "PT_PT": "PT",
    "PTPT": "PT",
    "PORTUGUES": "PT",
    "PORTUGUESA": "PT",
    "PORTUGUÊS": "PT",
    "PORTUGUÊSA": "PT",
    "PORTUGUESE": "PT",
    "BR": "PT",
    "EN": "ING",
    "EN-US": "ING",
    "EN-GB": "ING",
    "EN_UK": "ING",
    "ENGLISH": "ING",
    "INGLES": "ING",
    "INGLE": "ING",
    "INGLÊS": "ING",
    "ES": "ESP",
    "ES-ES": "ESP",
    "ES-MX": "ESP",
    "ES-419": "ESP",
    "ES-LA": "ESP",
    "ESPAÑOL": "ESP",
    "ESPANOL": "ESP",
    "ESPANHOL": "ESP",
    "SPANISH": "ESP",
    "FR": "FRAN",
    "FR-CA": "FRAN",
    "FR-BE": "FRAN",
    "FRANCES": "FRAN",
    "FRANCÊS": "FRAN",
    "FRANCAIS": "FRAN",
    "FRANÇAIS": "FRAN",
    "DE": "ALE",
    "DE-DE": "ALE",
    "DE-AT": "ALE",
    "DE-CH": "ALE",
    "GERMAN": "ALE",
    "GERMANO": "ALE",
    "GERMANIC": "ALE",
    "ALEMAO": "ALE",
    "ALEMÃO": "ALE",
    "DEUTSCH": "ALE",
    "BG": "BUL",
    "BULGARO": "BUL",
    "BÚLGARO": "BUL",
    "BULGARIAN": "BUL",
    "RO": "ROM",
    "ROMENO": "ROM",
    "ROMANIAN": "ROM",
    "ROMÂN": "ROM",
    "ROMANA": "ROM",
    "GR": "GREGO",
    "EL": "GREGO",
    "ELLINIKA": "GREGO",
    "GREEK": "GREGO",
    "IT": "ITA",
    "IT-IT": "ITA",
    "ITALIAN": "ITA",
    "ITALIANO": "ITA",
    "ITÁLIANO": "ITA",
    "PL": "POL",
    "PL-PL": "POL",
    "POLISH": "POL",
    "POLONES": "POL",
    "POLONÊS": "POL",
    "POLSKI": "POL",
    "NL": "HOLAND",
    "NL-NL": "HOLAND",
    "NL-BE": "HOLAND",
    "HOLANDES": "HOLAND",
    "HOLANDÊS": "HOLAND",
    "DUTCH": "HOLAND",
    "RU": "RUS",
    "RU-RU": "RUS",
    "RUSSO": "RUS",
    "RUSSIAN": "RUS",
    "РУССКИЙ": "RUS",
    "РУССКИИ": "RUS",
    "UK": "UKR",
    "UKRAINIAN": "UKR",
    "UCRANIANO": "UKR",
    "CS": "CHEC",
    "CZ": "CHEC",
    "CZECH": "CHEC",
    "TCHECO": "CHEC",
    "CESTINA": "CHEC",
    "SK": "SLO",
    "SLOVAK": "SLO",
    "ESLOVACO": "SLO",
    "HU": "HUN",
    "HUNGARIAN": "HUN",
    "HUNGARO": "HUN",
    "SR": "SER",
    "SERBIAN": "SER",
    "SÉRVIO": "SER",
    "SERVIO": "SER",
    "HR": "CRO",
    "CROATIAN": "CRO",
    "CROATA": "CRO",
    "SV": "SUE",
    "SV-SE": "SUE",
    "SWEDISH": "SUE",
    "SUECO": "SUE",
    "SVENSKA": "SUE",
    "DA": "DAN",
    "DA-DK": "DAN",
    "DANISH": "DAN",
    "DINAMARQUES": "DAN",
    "NO": "NOR",
    "NB": "NOR",
    "NORWEGIAN": "NOR",
    "NORUEGUES": "NOR",
    "FI": "FIN",
    "FINNISH": "FIN",
    "FINLANDES": "FIN",
    "IS": "ISL",
    "IS-IS": "ISL",
    "ICELANDIC": "ISL",
    "ISLANDES": "ISL",
    "TR": "TUR",
    "TURKISH": "TUR",
    "TURCO": "TUR",
    "AR": "ARA",
    "ARABIC": "ARA",
    "ARABE": "ARA",
    "العربية": "ARA",
    "HI": "HIN",
    "HINDI": "HIN",
    "हिंदी": "HIN",
    "BN": "BEN",
    "BENGALI": "BEN",
    "JA": "JAP",
    "JA-JP": "JAP",
    "JAPANESE": "JAP",
    "JAPONES": "JAP",
    "日本語": "JAP",
    "KO": "KOR",
    "KO-KR": "KOR",
    "KOREAN": "KOR",
    "COREANO": "KOR",
    "한국어": "KOR",
    "한국어": "KOR",
    "ZH": "CHI",
    "ZH-CN": "CHI",
    "ZH_CN": "CHI",
    "ZH-TW": "CHI",
    "ZH_TW": "CHI",
    "ZH-HK": "CHI",
    "ZH_HK": "CHI",
    "CHINESE": "CHI",
    "CHINES": "CHI",
    "中文": "CHI",
    "TH": "THA",
    "THAI": "THA",
    "TAILANDES": "THA",
    "ภาษาไทย": "THA",
    "VI": "VIE",
    "VIETNAMESE": "VIE",
    "VIETNAMES": "VIE",
    "TIENG VIET": "VIE",
    "TIENGVIET": "VIE",
    "MS": "MAL",
    "MALAY": "MAL",
    "MALAIO": "MAL",
    "ID": "IND",
    "INDONESIAN": "IND",
    "INDONESIO": "IND",
    "TL": "FIL",
    "TAGALOG": "FIL",
    "FILIPINO": "FIL",
    "FA": "PER",
    "FARSI": "PER",
    "PERSIAN": "PER",
    "PERSA": "PER",
    "HE": "HEB",
    "HEBREW": "HEB",
    "HEBRAICO": "HEB",
    "SW": "SWA",
    "SWAHILI": "SWA",
    "SUAILI": "SWA",
    "AF": "AFR",
    "AFRIKAANS": "AFR",
    "CATALAN": "CAT",
    "CATALAO": "CAT",
    "CATALA": "CAT",
    "CA": "CAT",
    "GL": "GALE",
    "GL-ES": "GALE",
    "GALEGO": "GALE",
    "GALICIAN": "GALE",
}

LANGUAGE_TRANSLATION_CODES: Dict[str, str] = {
    "PT": "pt",
    "ING": "en",
    "ESP": "es",
    "FRAN": "fr",
    "BUL": "bg",
    "ROM": "ro",
    "ALE": "de",
    "GREGO": "el",
    "ITA": "it",
    "POL": "pl",
    "HOLAND": "nl",
    "RUS": "ru",
    "UKR": "uk",
    "CHEC": "cs",
    "SLO": "sk",
    "HUN": "hu",
    "SER": "sr",
    "CRO": "hr",
    "SUE": "sv",
    "DAN": "da",
    "NOR": "nb",
    "FIN": "fi",
    "ISL": "is",
    "TUR": "tr",
    "ARA": "ar",
    "HIN": "hi",
    "BEN": "bn",
    "JAP": "ja",
    "KOR": "ko",
    "CHI": "zh-cn",
    "THA": "th",
    "VIE": "vi",
    "MAL": "ms",
    "IND": "id",
    "FIL": "tl",
    "PER": "fa",
    "HEB": "he",
    "SWA": "sw",
    "AFR": "af",
    "CAT": "ca",
    "GALE": "gl",
}


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize('NFKD', value or '')
    return ''.join(ch for ch in normalized if not unicodedata.combining(ch))


LANGUAGE_NAME_TO_CODE: Dict[str, str] = {
    _strip_accents(name).upper(): code for code, name in LANGUAGE_CODE_MAP.items()
}


def _fallback_google_api_translate(text: str, translator_target: str) -> Optional[str]:
    """Executa uma tradução utilizando a API pública do Google Translate."""

    if not text or not translator_target:
        return None

    fallback_url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "gtx",
        "sl": "auto",
        "tl": translator_target,
        "dt": "t",
        "q": text,
    }

    try:
        response = requests.get(fallback_url, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # pragma: no cover - depende de serviço externo
        logger.warning(
            "Falha na tradução alternativa para %s via API pública: %s",
            translator_target,
            exc,
        )
        return None

    if not isinstance(payload, list) or not payload:
        return None

    translated_segments = []
    for segment in payload[0] or []:
        if isinstance(segment, list) and segment:
            translated_segments.append(str(segment[0]))

    joined = "".join(translated_segments).strip()
    return joined or None


def _attempt_translate_text(text: str, target_code: Optional[str]) -> Tuple[Optional[str], bool]:
    """Tenta traduzir o texto para o código de idioma fornecido."""

    if not text or not target_code:
        return None, False

    translator_target = LANGUAGE_TRANSLATION_CODES.get(target_code)
    if not translator_target:
        return None, False

    cleaned_source = text.strip()

    # Lista de métodos de tradução a serem tentados em ordem de prioridade
    translators: List[Callable[[], Optional[str]]] = []

    if GoogleTranslator is not None:
        def _translate_with_deep_translator() -> Optional[str]:
            try:
                translated_value = GoogleTranslator(source="auto", target=translator_target).translate(text)
                if translated_value:
                    return str(translated_value)
                return None
            except Exception as exc:  # pragma: no cover - depende de serviço externo
                logger.warning("Falha ao traduzir texto para %s: %s", target_code, exc)
                return None

        translators.append(_translate_with_deep_translator)

    def _translate_with_fallback() -> Optional[str]:
        return _fallback_google_api_translate(text, translator_target)

    translators.append(_translate_with_fallback)

    for translator in translators:
        translated = translator()
        if translated and translated.strip():
            cleaned = translated.strip()
            return cleaned, cleaned != cleaned_source

    return None, False


def _prepare_intro_text(
    params: Dict[str, Any],
    language_hint: Optional[str] = None,
    progress_queue: Optional[Queue] = None,
    log_prefix: str = ""
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
                    "warning"
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

def _normalize_language_code(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    candidate = _strip_accents(str(value).strip()).upper()
    if not candidate:
        return None
    candidate = LANGUAGE_ALIASES.get(candidate, candidate)
    if candidate in LANGUAGE_CODE_MAP:
        return candidate
    if candidate in LANGUAGE_NAME_TO_CODE:
        return LANGUAGE_NAME_TO_CODE[candidate]
    return None


def _infer_language_code_from_name(name: str) -> Optional[str]:
    tokens = re.split(r"[\s._-]+", name) if name else []
    for token in tokens:
        normalized = _normalize_language_code(token)
        if normalized:
            return normalized
    return None


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


def _render_typing_frames(text: str, resolution: Tuple[int, int], frames_dir: str, font_path: Optional[str]) -> Tuple[int, float]:
    os.makedirs(frames_dir, exist_ok=True)
    width, height = resolution
    fps = 30
    cursor_symbol = '▋'

    try:
        if font_path and os.path.isfile(font_path):
            from PIL import ImageFont

            base_font = ImageFont.truetype(font_path, max(int(height * 0.07), 24))
        else:
            from PIL import ImageFont

            base_font = ImageFont.truetype("arial.ttf", max(int(height * 0.07), 24))
    except Exception:
        from PIL import ImageFont

        base_font = ImageFont.load_default()

    total_frames = 0
    clean_text = text.replace('\r\n', '\n')
    characters = list(clean_text)
    if not characters:
        characters = [' ']

    max_chars_per_line = max(20, int(width / max(base_font.size * 0.55, 1)))

    for index in range(len(characters) + 10):
        current = characters[:max(0, index)]
        display_text = ''.join(current)
        if index < len(characters):
            display_text += cursor_symbol
        elif index % 6 < 3:
            display_text += cursor_symbol

        wrapped_lines: List[str] = []
        for block in display_text.split('\n'):
            block = block.strip()
            wrapped_lines.extend(textwrap.wrap(block, width=max_chars_per_line) or [''])
        if not wrapped_lines:
            wrapped_lines = ['']

        img = Image.new('RGB', (width, height), color='black')
        draw = ImageDraw.Draw(img)
        line_height = base_font.size + 6
        total_text_height = line_height * len(wrapped_lines)
        y = (height - total_text_height) // 2
        for line in wrapped_lines:
            line_width = draw.textlength(line, font=base_font)
            x = (width - int(line_width)) // 2
            draw.text((x, y), line, font=base_font, fill='white')
            y += line_height

        frame_path = os.path.join(frames_dir, f"frame_{index:04d}.png")
        img.save(frame_path, format='PNG')
        total_frames += 1

    duration = total_frames / fps
    return total_frames, duration


def _synthesize_typing_audio(text: str, output_path: str, sample_rate: int = 44100) -> float:
    tone_duration = 0.045
    silence_duration = 0.055
    tone_freq = 850

    samples = array('h')
    amplitude = int(0.35 * 32767)

    for ch in text:
        if ch.isspace():
            silence_samples = int(sample_rate * (tone_duration + silence_duration))
            samples.extend([0] * silence_samples)
            continue
        tone_samples = int(sample_rate * tone_duration)
        for n in range(tone_samples):
            envelope = math.exp(-3 * (n / max(1, tone_samples)))
            value = int(amplitude * envelope * math.sin(2 * math.pi * tone_freq * n / sample_rate))
            samples.append(value)
        silence_samples = int(sample_rate * silence_duration)
        samples.extend([0] * silence_samples)

    samples.extend([0] * int(sample_rate * 0.2))

    with wave.open(output_path, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(samples.tobytes())

    return len(samples) / sample_rate


def _create_typing_intro_clip(
    text: str,
    resolution: Tuple[int, int],
    params: Dict[str, Any],
    temp_dir: str,
    progress_queue: Queue,
    cancel_event: threading.Event,
    log_prefix: str,
) -> Optional[Dict[str, Any]]:
    intro_temp_dir = tempfile.mkdtemp(prefix="typing-intro-", dir=temp_dir)
    frames_dir = os.path.join(intro_temp_dir, "frames")
    font_path = params.get('subtitle_style', {}).get('font_file') if params.get('subtitle_style') else None

    try:
        total_frames, frames_duration = _render_typing_frames(text, resolution, frames_dir, font_path)
        audio_path = os.path.join(intro_temp_dir, "typing_audio.wav")
        audio_duration = _synthesize_typing_audio(text, audio_path)

        fps = 30
        progress_queue.put(("status", f"[{log_prefix}] Criando animação da introdução...", "info"))
        cmd_video = [
            params['ffmpeg_path'], '-y',
            '-framerate', str(fps),
            '-i', os.path.join(frames_dir, 'frame_%04d.png'),
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            os.path.join(intro_temp_dir, 'typing_intro_silent.mp4')
        ]

        if not _execute_ffmpeg(cmd_video, max(frames_duration, 1), None, cancel_event, f"{log_prefix} (Intro Frames)", progress_queue):
            raise RuntimeError("Falha ao gerar a animação da introdução")

        progress_queue.put(("status", f"[{log_prefix}] Misturando áudio da digitação...", "info"))
        final_intro_path = os.path.join(intro_temp_dir, 'typing_intro.mp4')
        cmd_merge = [
            params['ffmpeg_path'], '-y',
            '-i', os.path.join(intro_temp_dir, 'typing_intro_silent.mp4'),
            '-i', audio_path,
            '-c:v', 'copy',
            '-c:a', 'aac', '-b:a', '160k',
            '-shortest',
            final_intro_path
        ]

        total_duration = max(frames_duration, audio_duration)
        if not _execute_ffmpeg(cmd_merge, total_duration, None, cancel_event, f"{log_prefix} (Intro Áudio)", progress_queue):
            raise RuntimeError("Falha ao sincronizar áudio da introdução")

        return {
            'path': final_intro_path,
            'temp_dir': intro_temp_dir,
            'duration': total_duration,
        }
    except Exception as exc:
        shutil.rmtree(intro_temp_dir, ignore_errors=True)
        progress_queue.put(("status", f"[{log_prefix}] Erro ao gerar a introdução: {exc}", "error"))
        return None


def _combine_intro_with_main(
    intro_info: Dict[str, Any],
    main_path: str,
    final_output_path: str,
    params: Dict[str, Any],
    progress_queue: Queue,
    cancel_event: threading.Event,
    log_prefix: str,
) -> bool:
    intro_path = intro_info['path']
    ffmpeg_path = params['ffmpeg_path']

    intro_props = _probe_media_properties(intro_path, ffmpeg_path) or {}
    main_props = _probe_media_properties(main_path, ffmpeg_path) or {}

    intro_duration = float(intro_props.get('format', {}).get('duration', intro_info.get('duration', 5)))
    main_duration = float(main_props.get('format', {}).get('duration', 0))
    fade_duration = 0.8 if intro_duration >= 1.6 else max(0.4, intro_duration / 2)
    offset = max(0.0, intro_duration - fade_duration)

    filter_parts = [
        "[0:v]format=yuv420p,setsar=1[v0]",
        "[1:v]format=yuv420p,setsar=1[v1]",
        f"[v0][v1]xfade=transition=fade:duration={fade_duration}:offset={offset}[vout]",
    ]
    map_args = ['-map', '[vout]']

    intro_has_audio = any(stream.get('codec_type') == 'audio' for stream in intro_props.get('streams', []))
    main_has_audio = any(stream.get('codec_type') == 'audio' for stream in main_props.get('streams', []))

    if intro_has_audio and main_has_audio:
        filter_parts.append(f"[0:a]apad=pad_dur={fade_duration}[introa]")
        filter_parts.append(f"[introa][1:a]acrossfade=d={fade_duration}[aout]")
        map_args.extend(['-map', '[aout]'])
    elif intro_has_audio:
        filter_parts.append(f"[0:a]afade=t=out:st={offset}:d={fade_duration}[introa]")
        map_args.extend(['-map', '[introa]'])
    elif main_has_audio:
        delay_ms = int(intro_duration * 1000)
        filter_parts.append(f"[1:a]adelay={delay_ms}|{delay_ms}[aout]")
        map_args.extend(['-map', '[aout]'])

    progress_queue.put(("status", f"[{log_prefix}] Mesclando introdução digitada ao vídeo final...", "info"))

    filter_complex = ';'.join(filter_parts)
    cmd = [
        ffmpeg_path, '-y',
        '-i', intro_path,
        '-i', main_path,
        '-filter_complex', filter_complex,
        *map_args,
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
    ]

    if any(label in map_args for label in ('[aout]', '[introa]')):
        cmd.extend(['-c:a', 'aac', '-b:a', '192k'])
    else:
        cmd.append('-an')

    cmd.extend(['-movflags', '+faststart', final_output_path])

    total_duration = intro_duration + main_duration
    return _execute_ffmpeg(cmd, total_duration or intro_duration or 5, None, cancel_event, f"{log_prefix} (Intro Merge)", progress_queue)


# --- Classes Auxiliares ---

class FFmpegProcessManager:
    """Gerencia processos FFmpeg em execução para garantir a limpeza na saída."""
    def __init__(self):
        self.active_processes: Dict[int, subprocess.Popen] = {}
        self.lock = threading.Lock()
        atexit.register(self.shutdown)

    def add(self, process: subprocess.Popen):
        with self.lock:
            self.active_processes[process.pid] = process
            logger.debug(f"Processo {process.pid} adicionado. Total: {len(self.active_processes)}")

    def remove(self, process: subprocess.Popen):
        with self.lock:
            if process.pid in self.active_processes:
                del self.active_processes[process.pid]
                logger.debug(f"Processo {process.pid} removido. Restantes: {len(self.active_processes)}")

    def terminate_all(self):
        with self.lock:
            if not self.active_processes: return
            logger.info(f"Encerrando {len(self.active_processes)} processo(s) FFmpeg ativo(s)...")
            processes_to_kill = list(self.active_processes.values())
        
        for process in processes_to_kill:
            try:
                if process.poll() is None:
                    logger.warning(f"Forçando o encerramento do processo {process.pid}...")
                    process.terminate()
                    try: process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        logger.error(f"O processo {process.pid} não encerrou, matando.")
                        process.kill()
            except Exception as e: logger.error(f"Erro ao encerrar o processo {process.pid}: {e}")
        
        with self.lock: self.active_processes.clear()

    def shutdown(self):
        self.terminate_all()

process_manager = FFmpegProcessManager()


def _infer_language_code_from_filename(filename: str) -> Optional[str]:
    if not filename:
        return None
    stem = Path(filename).stem
    tokens = re.split(r'[^A-Za-zÀ-ÖØ-öø-ÿ]+', stem)
    for token in reversed(tokens):
        normalized = _normalize_language_code(token)
        if normalized:
            return normalized
    return None

def _stream_reader(stream: Optional[IO], line_queue: Queue):
    if not stream:
        return

    encoding = locale.getpreferredencoding(False) or 'utf-8'

    try:
        # Ler linha a linha para garantir que atualizações frequentes do FFmpeg
        # cheguem imediatamente à fila de processamento. O uso de "read" com
        # blocos grandes pode provocar travamentos aparentes quando o FFmpeg
        # escreve apenas pequenas mensagens de progresso.
        while True:
            chunk = stream.readline()
            if not chunk:
                break

            if isinstance(chunk, bytes):
                decoded = chunk.decode(encoding, errors='replace')
            else:
                decoded = chunk

            line_queue.put(decoded)
    except Exception as e:
        logger.warning(f"O leitor de stream encontrou um erro: {e}")
    finally:
        try:
            stream.close()
        except Exception:
            pass

def _execute_ffmpeg(cmd: List[str], duration: float, progress_callback: Optional[Callable[[float], None]], cancel_event: threading.Event, log_prefix: str, progress_queue: Queue) -> bool:
    ffmpeg_path = cmd[0]
    if not os.path.isfile(ffmpeg_path):
        error_msg = f"ERRO FATAL: O caminho para o FFmpeg é inválido: '{ffmpeg_path}'"
        progress_queue.put(("status", error_msg, "error"))
        logger.critical(f"FFmpeg executable check failed: '{ffmpeg_path}'")
        return False

    logger.info(f"[{log_prefix}] Executing FFmpeg: {ffmpeg_path}")
    progress_queue.put(("status", f"[{log_prefix}] Iniciando processo FFmpeg...", "info"))

    cmd_with_progress = [ffmpeg_path] + ["-progress", "pipe:1", "-nostats"] + cmd[1:]
    creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0

    logger.debug(f"[{log_prefix}] Comando FFmpeg: {' '.join(map(str, cmd_with_progress))}")

    try:
        process = subprocess.Popen(cmd_with_progress, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creation_flags, shell=False)
    except (FileNotFoundError, OSError) as e:
        logger.critical(f"Erro ao executar o FFmpeg em '{ffmpeg_path}': {e}", exc_info=True)
        progress_queue.put(("status", f"Erro crítico ao executar o FFmpeg: {e}", "error"))
        return False

    process_manager.add(process)
    
    output_queue = Queue()
    stdout_thread = threading.Thread(target=_stream_reader, args=(process.stdout, output_queue), daemon=True)
    stderr_thread = threading.Thread(target=_stream_reader, args=(process.stderr, output_queue), daemon=True)
    stdout_thread.start(); stderr_thread.start()

    full_output = ""
    last_reported_pct = 0.0
    stall_warning_threshold = 45.0
    stall_warning_interval = 15.0
    stall_abort_threshold = 120.0
    last_activity_time = time.monotonic()
    last_warning_bucket = 0
    stalled = False
    last_nonempty_line = ""

    while process.poll() is None:
        if cancel_event.is_set():
            logger.warning(f"[{log_prefix}] Cancelamento solicitado. Encerrando FFmpeg {process.pid}.")
            progress_queue.put(("status", f"[{log_prefix}] Cancelamento em andamento...", "warning"))
            process.terminate(); break

        try:
            chunk = output_queue.get(timeout=0.1)
            last_activity_time = time.monotonic()
            last_warning_bucket = 0
            for line in chunk.split('\n'):
                full_output += line + '\n'
                stripped = line.strip()
                if "out_time_ms=" in stripped or "out_time_us=" in stripped or stripped.startswith("out_time="):
                    key, _, value = stripped.partition("=")
                    key = key.strip()
                    value = value.strip()

                    current_time_sec = None
                    if key == "out_time_ms" and value.isdigit():
                        current_time_sec = int(value) / 1_000_000
                    elif key == "out_time_us" and value.isdigit():
                        current_time_sec = int(value) / 1_000_000
                    elif key == "out_time" and value:
                        try:
                            h, m, s = value.split(":")
                            current_time_sec = int(h) * 3600 + int(m) * 60 + float(s)
                        except ValueError:
                            current_time_sec = None

                    if current_time_sec is not None and duration > 0:
                        progress_pct = min(current_time_sec / duration, 1.0)
                        if progress_callback:
                            progress_callback(progress_pct)
                        if progress_pct - last_reported_pct >= 0.01:
                            progress_queue.put(("status", f"[{log_prefix}] {int(progress_pct*100)}% concluído", "info"))
                            last_reported_pct = progress_pct
                else:
                    stripped_line = line.strip()
                    if stripped_line:
                        last_nonempty_line = stripped_line
                        logger.debug(f"[{log_prefix}/ffmpeg] {stripped_line}")
        except Empty:
            elapsed = time.monotonic() - last_activity_time
            if elapsed >= stall_abort_threshold:
                stalled = True
                logger.warning(
                    f"[{log_prefix}] Sem progresso por {int(elapsed)}s. "
                    f"Abortando processo FFmpeg {process.pid} por possível travamento."
                )
                progress_queue.put((
                    "status",
                    f"[{log_prefix}] Nenhum progresso há {int(elapsed)}s. Abortando renderização atual...",
                    "warning",
                ))
                process.terminate()
                break

            warning_elapsed = elapsed - stall_warning_threshold
            if warning_elapsed >= 0:
                warning_bucket = int(warning_elapsed // stall_warning_interval) + 1
                if warning_bucket > last_warning_bucket:
                    last_warning_bucket = warning_bucket
                    warn_seconds = int(stall_warning_threshold + stall_warning_interval * (warning_bucket - 1))
                    progress_queue.put((
                        "status",
                        f"[{log_prefix}] Sem progresso há {warn_seconds}s… processo pode estar lento ou travado.",
                        "info",
                    ))
            continue

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        logger.error(f"[{log_prefix}] Processo FFmpeg não encerrou após sinal de término. Forçando kill.")
        process.kill()
        process.wait()
    process_manager.remove(process)

    while not output_queue.empty():
        full_output += output_queue.get_nowait()

    if cancel_event.is_set():
        logger.warning(f"[{log_prefix}] Processo cancelado.")
        return False

    if process.returncode == 0 and not stalled:
        logger.info(f"[{log_prefix}] Comando FFmpeg concluído com sucesso.")
        if progress_callback:
            progress_callback(1.0)
        return True
    else:
        if stalled and process.returncode == 0:
            # Garantir que travamentos detectados não sejam reportados como sucesso silencioso
            process.returncode = -1
        if stalled:
            logger.error(f"[{log_prefix}] FFmpeg interrompido por falta de progresso.")
            stall_detail = last_nonempty_line or "Nenhuma mensagem adicional do FFmpeg."
            progress_queue.put((
                "status",
                f"[{log_prefix}] FFmpeg interrompido por falta de progresso. Última saída conhecida: {stall_detail}",
                "error",
            ))
        logger.error(f"[{log_prefix}] FFmpeg falhou com o código {process.returncode}.")
        logger.error(f"[{log_prefix}] Log FFmpeg:\n{full_output}")
        error_lines = [line for line in full_output.lower().splitlines() if 'error' in line or 'invalid' in line]
        if not error_lines and last_nonempty_line:
            error_lines = [last_nonempty_line]
        error_snippet = "\n".join(error_lines[-3:]) if error_lines else "\n".join(full_output.strip().split("\n")[-5:])

        progress_queue.put(("status", f"[{log_prefix}] ERRO no FFmpeg: {error_snippet}", "error"))
        return False


def _escape_ffmpeg_path(path_str: str) -> str:
    """Escapa um caminho para ser usado dentro de um filtergraph do FFmpeg."""
    return (
        str(Path(path_str))
        .replace('\\', '/')
        .replace(':', '\\:')
        .replace("'", r"\'")
    )

def _probe_media_properties(path: str, ffmpeg_path: str) -> Optional[Dict]:
    if not path or not os.path.isfile(path): return None
    
    ffprobe_exe_name = "ffprobe.exe" if platform.system() == "Windows" else "ffprobe"
    
    final_ffprobe_path = ""
    if ffmpeg_path and os.path.isfile(ffmpeg_path):
        derived_path = os.path.normpath(os.path.join(Path(ffmpeg_path).parent, ffprobe_exe_name))
        if os.path.isfile(derived_path):
            final_ffprobe_path = derived_path

    if not final_ffprobe_path:
        found_in_path = shutil.which(ffprobe_exe_name)
        if found_in_path:
            logger.info(f"ffprobe não encontrado via caminho do FFmpeg. Usando ffprobe do PATH: {found_in_path}")
            final_ffprobe_path = found_in_path
        else:
            logger.error(f"ffprobe não encontrado. Verifique o caminho do FFmpeg ou o PATH do sistema.")
            return None
        
    try:
        cmd = [final_ffprobe_path, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", os.path.normpath(path)]
        creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=15, creationflags=creation_flags, encoding='utf-8', errors='ignore')
        return json.loads(result.stdout)
    except FileNotFoundError:
        logger.error(f"ffprobe não pôde ser executado em '{final_ffprobe_path}'. Verifique a instalação do FFmpeg.")
        return None
    except Exception as e:
        logger.warning(f"Não foi possível obter propriedades de '{Path(path).name}': {e}")
        return None

def _parse_resolution(res_str: str) -> Tuple[int, int]:
    match = re.search(r'(\d+)\s*[xX]\s*(\d+)', res_str)
    return (int(match.group(1)), int(match.group(2))) if match else (1920, 1080)

def _get_codec_params(params: Dict, force_reencode=False) -> List[str]:
    video_codec_choice = params.get('video_codec', 'Automático')
    available_encoders = params.get('available_encoders', [])
    
    if not force_reencode:
        logger.info("Nenhuma recodificação de vídeo necessária. Usando '-c:v copy'.")
        return ["-c:v", "copy"]

    encoder = "libx264"
    codec_flags = ["-preset", "veryfast", "-crf", "23"]
    
    use_gpu = (video_codec_choice == 'Automático' and any(e in available_encoders for e in ["h264_nvenc", "hevc_nvenc"])) or "GPU" in video_codec_choice

    if use_gpu:
        logger.info("Tentando usar aceleração por GPU (NVENC)...")
        if "h264_nvenc" in available_encoders:
            encoder, codec_flags = "h264_nvenc", ["-preset", "p2", "-cq", "23", "-rc-lookahead", "8"]
            logger.info(f"Selecionado encoder GPU: h264_nvenc com preset p2")
        elif "hevc_nvenc" in available_encoders:
            encoder, codec_flags = "hevc_nvenc", ["-preset", "p2", "-cq", "23", "-rc-lookahead", "8"]
            logger.info(f"Selecionado encoder GPU: hevc_nvenc com preset p2")
        else:
            logger.warning("Aceleração por GPU solicitada, mas nenhum encoder NVENC foi encontrado. Voltando para CPU (libx264).")
    else:
        codec_flags = ["-preset", "superfast", "-crf", "26"]
        logger.info(f"Selecionado encoder CPU: libx264 com preset superfast")

    return ["-c:v", encoder, *codec_flags, "-pix_fmt", "yuv420p"]

def _create_styled_ass_from_srt(srt_path: str, style_params: Dict, temp_dir: str, resolution: Tuple[int, int]) -> Optional[str]:
    if not srt_path or not os.path.exists(srt_path):
        return None

    try:
        def to_ass_color(hex_color: str) -> str:
            hex_color = hex_color.lstrip('#')
            if len(hex_color) != 6: return "&H00FFFFFF"
            r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
            return f"&H00{b}{g}{r}".upper()

        def srt_time_to_ass(srt_time: str) -> str:
            try:
                time_parts = srt_time.split(',')
                hms = time_parts[0]
                ms = time_parts[1]
                cs = int(int(ms) / 10)
                h, m, s = hms.split(':')
                return f"{int(h)}:{m}:{s}.{cs:02d}"
            except Exception:
                return srt_time.replace(',', '.')

        pos_map = style_params.get('position_map', {})
        alignment = int(pos_map.get(style_params.get('position'), 2))
        margin_v = 0 if alignment in (4, 5, 6) else int(int(style_params.get('fontsize', 48)) * 0.7)
        
        style_format = "Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
        style_values = [
            "CustomStyle",
            Path(style_params.get('font_file')).stem if style_params.get('font_file') else 'Arial',
            int(style_params.get('fontsize', 48)),
            to_ass_color(style_params.get('text_color', '#FFFFFF')),
            "&H00FFFFFF",
            to_ass_color(style_params.get('outline_color', '#000000')),
            "&H00000000",
            -1 if style_params.get('bold', True) else 0,
            -1 if style_params.get('italic', False) else 0,
            0, 0, 100, 100, 0, 0.0, 1, 2, 1,
            alignment,
            10, 10, margin_v, 1
        ]
        style_line = "Style: " + ",".join(map(str, style_values))

        ass_content = [
            "[Script Info]", "Title: Legenda Gerada", f"PlayResX: {resolution[0]}",
            f"PlayResY: {resolution[1]}", "ScriptType: v4.00+", "", "[V4+ Styles]",
            f"Format: {style_format}", style_line, "", "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
        ]

        with open(srt_path, 'r', encoding='utf-8', errors='ignore') as f:
            srt_text = f.read()
        
        srt_blocks = re.findall(r'(\d+)\s*\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\s*\n(.*?)(?=\n\n|\Z)', srt_text, re.DOTALL)

        for block in srt_blocks:
            _, start_time, end_time, text = block
            clean_text = re.sub(r'<.*?>', '', text).strip().replace('\n', '\\N')
            
            event_line = f"Dialogue: 0,{srt_time_to_ass(start_time)},{srt_time_to_ass(end_time)},CustomStyle,,0,0,0,," + clean_text
            ass_content.append(event_line)

        ass_path = os.path.join(temp_dir, f"styled_{Path(srt_path).stem}.ass")
        with open(ass_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(ass_content))
        
        logger.info(f"Arquivo SRT '{Path(srt_path).name}' convertido para ASS estilizado em '{ass_path}'")
        return ass_path

    except Exception as e:
        logger.error(f"Falha ao converter SRT para ASS: {e}", exc_info=True)
        return srt_path

def process_entrypoint(params: Dict[str, Any], progress_queue: Queue, cancel_event: threading.Event):
    temp_dir = tempfile.mkdtemp(prefix="kyle-editor-")
    logger.info(f"Processamento iniciado. Dir temporário: {temp_dir}")
    progress_queue.put(("status", "Diretório temporário criado.", "info"))
    success = False
    try:
        if cancel_event.is_set(): raise InterruptedError("Cancelado antes de iniciar.")
        
        media_type = params.get('media_type')
        if media_type == 'batch_video':
            success = _run_batch_video_processing(params, progress_queue, cancel_event, temp_dir)
        elif media_type == 'batch_image':
            success = _run_batch_image_processing(params, progress_queue, cancel_event, temp_dir)
        elif media_type == 'batch_mixed':
            success = _run_batch_mixed_processing(params, progress_queue, cancel_event, temp_dir)
        elif media_type == 'batch_image_hierarchical':
            success = _run_hierarchical_batch_image_processing(params, progress_queue, cancel_event, temp_dir)
        elif media_type == 'image_folder':
            success = _run_slideshow_processing(params, progress_queue, cancel_event, temp_dir)
        else:
            success = _run_single_item_processing(params, progress_queue, cancel_event, temp_dir)
            
    except InterruptedError:
        logger.warning("Processamento interrompido pelo usuário.")
        success = False
    except Exception as e:
        logger.critical(f"Exceção não tratada na thread de processamento: {e}", exc_info=True)
        progress_queue.put(("status", f"Erro CRÍTICO: {e}", "error"))
    finally:
        try: shutil.rmtree(temp_dir)
        except Exception as e: logger.error(f"Falha ao limpar o diretório temporário {temp_dir}: {e}")
        
        gc.collect()
        
        cancelled = cancel_event.is_set()
        progress_queue.put(("finish", success and not cancelled))
        final_message = "Processo cancelado pelo usuário." if cancelled else ("Processo concluído com sucesso!" if success else "Processo falhou.")
        final_tag = "warning" if cancelled else ("success" if success else "error")
        progress_queue.put(("status", final_message, final_tag))
        logger.info(f"Processamento finalizado. Sucesso: {success}, Cancelado: {cancelled}")

def _run_single_item_processing(params: Dict[str, Any], progress_queue: Queue, cancel_event: threading.Event, temp_dir: str) -> bool:
    if cancel_event.is_set(): return False
    
    final_params = params.copy()
    narration_path = params.get('narration_file_single')

    selected_language = params.get('single_language_code')
    normalized_language = None
    if isinstance(selected_language, str) and selected_language.lower() != 'auto':
        normalized_language = _normalize_language_code(selected_language)

    if not normalized_language:
        normalized_language = _infer_language_code_from_filename(narration_path or params.get('media_path_single'))

    if normalized_language:
        final_params['current_language_code'] = normalized_language
    if narration_path and os.path.isfile(narration_path):
        output_name = f"video_final_{Path(narration_path).stem}.mp4"
        final_params['output_filename_single'] = output_name
        progress_queue.put(("status", f"Nome do arquivo de saída definido para: {output_name}", "info"))

    music_paths = [params.get('music_file_single')] if params.get('music_file_single') else []
    final_params['current_language_code'] = params.get('intro_language_code')

    return _perform_final_pass(
        params=final_params,
        base_video_path=params.get('media_path_single'),
        narration_path=params.get('narration_file_single'),
        music_paths=music_paths,
        subtitle_path=params.get('subtitle_file_single'),
        progress_queue=progress_queue,
        cancel_event=cancel_event,
        temp_dir=temp_dir,
        log_prefix="Vídeo Único"
    )

def _run_slideshow_processing(params: Dict[str, Any], progress_queue: Queue, cancel_event: threading.Event, temp_dir: str) -> bool:
    if cancel_event.is_set(): return False
    
    log_prefix = "Slideshow"
    image_folder = params.get('media_path_single')
    narration_path = params.get('narration_file_single')

    if not narration_path or not os.path.isfile(narration_path):
        progress_queue.put(("status", f"[{log_prefix}] Erro: Arquivo de narração é obrigatório.", "error")); return False
    if not image_folder or not os.path.isdir(image_folder):
        progress_queue.put(("status", f"[{log_prefix}] Erro: Pasta de imagens é obrigatória.", "error")); return False

    narration_props = _probe_media_properties(narration_path, params['ffmpeg_path'])
    if not narration_props or 'format' not in narration_props or 'duration' not in narration_props['format']:
        progress_queue.put(("status", f"[{log_prefix}] Erro CRÍTICO: Não foi possível ler a duração da narração.", "error")); return False
    
    final_duration = float(narration_props['format']['duration'])
    if params.get('add_fade_out'):
        final_duration += params.get('fade_out_duration', 10)

    supported_ext = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
    images = sorted([p for p in Path(image_folder).iterdir() if p.is_file() and p.suffix.lower() in supported_ext])
    
    if not images:
        progress_queue.put(("status", f"[{log_prefix}] Erro: Nenhuma imagem encontrada em {image_folder}.", "error")); return False

    base_video_path, success = _process_images_in_chunks(params, images, final_duration, temp_dir, progress_queue, cancel_event, log_prefix)
    
    if not success:
        return False

    if cancel_event.is_set(): return False
    
    progress_queue.put(("status", f"[{log_prefix}] Adicionando áudio e legendas...", "info"))
    
    final_params = params.copy()
    selected_language = params.get('single_language_code')
    normalized_language = None
    if isinstance(selected_language, str) and selected_language.lower() != 'auto':
        normalized_language = _normalize_language_code(selected_language)
    if not normalized_language:
        normalized_language = _infer_language_code_from_filename(narration_path)
    if normalized_language:
        final_params['current_language_code'] = normalized_language
    if narration_path and os.path.isfile(narration_path):
        output_name = f"video_final_{Path(narration_path).stem}.mp4"
        final_params['output_filename_single'] = output_name
        progress_queue.put(("status", f"Nome do arquivo de saída definido para: {output_name}", "info"))

    music_paths = [params.get('music_file_single')] if params.get('music_file_single') else []
    final_params['current_language_code'] = params.get('intro_language_code')

    return _perform_final_pass(
        params=final_params,
        base_video_path=base_video_path,
        narration_path=narration_path,
        music_paths=music_paths,
        subtitle_path=params.get('subtitle_file_single'),
        progress_queue=progress_queue,
        cancel_event=cancel_event,
        temp_dir=temp_dir,
        log_prefix=log_prefix
    )

def _sanitize_image(image_path: Path, temp_dir: str, log_prefix: str, progress_queue: Queue) -> Optional[Path]:
    try:
        sanitized_path = Path(temp_dir) / f"sanitized_{image_path.stem}.png"
        with Image.open(image_path) as img:
            img.convert("RGBA").save(sanitized_path, "PNG")
        return sanitized_path
    except Exception as e:
        logger.error(f"[{log_prefix}] Falha ao processar a imagem '{image_path.name}': {e}. Pulando esta imagem.")
        progress_queue.put(("status", f"[{log_prefix}] AVISO: Imagem '{image_path.name}' parece corrompida e será ignorada.", "warning"))
        return None


def _create_video_chunk_from_images(
    params: Dict, 
    image_chunk: List[Path], 
    output_chunk_path: str, 
    progress_queue: Queue, 
    cancel_event: threading.Event, 
    log_prefix: str,
    temp_dir: str
) -> bool:
    
    sanitized_images = []
    for img_path in image_chunk:
        sanitized_path = _sanitize_image(img_path, temp_dir, log_prefix, progress_queue)
        if sanitized_path:
            sanitized_images.append(sanitized_path)

    if not sanitized_images:
        logger.error(f"[{log_prefix}] Nenhuma imagem válida no lote após a sanitização.")
        return False

    img_duration = params.get('image_duration', 5)
    transition_name = params.get('slideshow_transition', 'fade')
    transition_duration = params.get('slideshow_transition_duration', 1)
    motion = params.get('slideshow_motion', 'Zoom In')
    w, h = _parse_resolution(params['resolution'])
    framerate = 30
    
    inputs, filter_chains = [], []

    for img_path in sanitized_images:
        inputs.extend(["-loop", "1", "-framerate", str(framerate), "-t", str(img_duration), "-i", str(img_path.resolve())])

    for img_idx in range(len(sanitized_images)):
        zoompan_filter = ""
        frames = int(img_duration * framerate)
        if motion != 'Nenhum':
            zoom_rate = 0.15
            zoom_step = zoom_rate / frames
            if motion == 'Zoom In': zoompan_filter = f",zoompan=z='min(zoom+{zoom_step},1.15)':s={w}x{h}:d={frames}:fps={framerate}"
            elif motion == 'Zoom Out': zoompan_filter = f",zoompan=z='if(eq(on,1),{1+zoom_rate},max(zoom-{zoom_step},1))':s={w}x{h}:d={frames}:fps={framerate}"
            elif motion == 'Pan Direita': zoompan_filter = f",zoompan=z=1.1:x='(iw-iw/1.1)/{frames}*on':y='(ih-ih/1.1)/2':s={w}x{h}:d={frames}:fps={framerate}"
            elif motion == 'Pan Esquerda': zoompan_filter = f",zoompan=z=1.1:x='iw/1.1-((iw-iw/1.1)/{frames}*on)':y='(ih-ih/1.1)/2':s={w}x{h}:d={frames}:fps={framerate}"
        
        filter_chains.append(f"[{img_idx}:v]scale={w}x{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1{zoompan_filter}[v{img_idx}]")

    last_stream = "[v0]"
    if len(sanitized_images) > 1 and transition_name != 'none':
        for img_idx in range(1, len(sanitized_images)):
            offset = img_idx * (img_duration - transition_duration)
            output_stream = f"[chain{img_idx}]"
            filter_chains.append(f"{last_stream}[v{img_idx}]xfade=transition={transition_name}:duration={transition_duration}:offset={offset}{output_stream}")
            last_stream = output_stream
    else:
        concat_streams = "".join([f"[v{img_idx}]" for img_idx in range(len(sanitized_images))])
        filter_chains.append(f"{concat_streams}concat=n={len(sanitized_images)}[vout]")
        last_stream = "[vout]"

    codec_params = _get_codec_params(params, force_reencode=True)
    
    chunk_duration = (len(sanitized_images) * img_duration) - ((len(sanitized_images) - 1) * transition_duration if len(sanitized_images) > 1 and transition_name != 'none' else 0)
    
    cmd_chunk = [
        params['ffmpeg_path'], '-y', *inputs,
        '-filter_complex', ";".join(filter_chains),
        '-map', last_stream, *codec_params,
        '-r', str(framerate), '-t', str(chunk_duration),
        output_chunk_path
    ]
    
    def chunk_progress_update(pct):
        progress_queue.put(("progress", pct))

    return _execute_ffmpeg(cmd_chunk, chunk_duration, chunk_progress_update, cancel_event, log_prefix, progress_queue)


def _process_images_in_chunks(params: Dict, images: List[Path], final_duration: float, temp_dir: str, progress_queue: Queue, cancel_event: threading.Event, log_prefix: str) -> Tuple[Optional[str], bool]:
    CHUNK_SIZE = 15
    
    if not images:
        progress_queue.put(("status", f"[{log_prefix}] Erro: Nenhuma imagem fornecida para processamento.", "error")); return None, False

    img_duration = params.get('image_duration', 5)
    transition_name = params.get('slideshow_transition', 'fade')
    transition_duration = params.get('slideshow_transition_duration', 1)
    
    effective_img_duration = img_duration - transition_duration if transition_name != 'none' and len(images) > 1 else img_duration
    if effective_img_duration <= 0:
        progress_queue.put(("status", f"[{log_prefix}] Erro: Duração da imagem deve ser maior que a transição.", "error")); return None, False
    num_images_needed = ceil(final_duration / effective_img_duration) if effective_img_duration > 0 else len(images)
    images_to_use = (images * (num_images_needed // len(images) + 1))[:max(2, num_images_needed)]

    num_chunks = ceil(len(images_to_use) / CHUNK_SIZE)
    chunk_video_paths = []

    image_temp_dir = tempfile.mkdtemp(prefix="sanitized-images-", dir=temp_dir)

    for i in range(num_chunks):
        if cancel_event.is_set(): return None, False
        
        chunk_log_prefix = f"{log_prefix} (Lote de Imagens {i+1}/{num_chunks})"
        progress_queue.put(("status", f"[{chunk_log_prefix}] Processando imagens...", "info"))
        
        start_index = i * CHUNK_SIZE
        end_index = start_index + CHUNK_SIZE
        image_chunk = images_to_use[start_index:end_index]
        
        if not image_chunk: continue

        chunk_output_path = os.path.normpath(os.path.join(temp_dir, f"chunk_{i}.ts"))
        
        if not _create_video_chunk_from_images(params, image_chunk, chunk_output_path, progress_queue, cancel_event, chunk_log_prefix, image_temp_dir):
            progress_queue.put(("status", f"[{chunk_log_prefix}] Falha ao criar o lote de vídeo.", "error")); return None, False
        
        chunk_video_paths.append(chunk_output_path)
        progress_queue.put(("batch_progress", (i + 1) / (num_chunks + 1)))

    if cancel_event.is_set(): return None, False

    progress_queue.put(("status", f"[{log_prefix}] Montando vídeo final...", "info"))
    concat_list_path = os.path.join(temp_dir, 'concat_list.txt')
    with open(concat_list_path, 'w', encoding='utf-8') as f:
        for path in chunk_video_paths: f.write(f"file '{Path(path).as_posix()}'\n")

    base_video_path = os.path.normpath(os.path.join(temp_dir, "slideshow_stitched.mp4"))
    cmd_concat = [
        params['ffmpeg_path'], '-y', '-f', 'concat', '-safe', '0', '-i', concat_list_path,
        '-c', 'copy', base_video_path
    ]
    if not _execute_ffmpeg(cmd_concat, 0, None, cancel_event, f"{log_prefix} (Montagem)", progress_queue):
        progress_queue.put(("status", f"[{log_prefix}] Falha ao concatenar clipes.", "error")); return None, False

    progress_queue.put(("batch_progress", 1.0))
    return base_video_path, True

def _create_concatenated_audio(
    audio_paths: List[str], 
    output_path: str, 
    temp_dir: str, 
    params: Dict, 
    cancel_event: threading.Event, 
    progress_queue: Queue,
    log_prefix: str
) -> bool:
    if not audio_paths:
        return False
    
    progress_queue.put(("status", f"[{log_prefix}] Pré-processando {len(audio_paths)} faixas de música...", "info"))
    
    concat_list_path = os.path.join(temp_dir, 'music_concat_list.txt')
    try:
        with open(concat_list_path, 'w', encoding='utf-8') as f:
            for path in audio_paths:
                f.write(f"file '{Path(path).as_posix()}'\n")
    except IOError as e:
        progress_queue.put(("status", f"[{log_prefix}] Erro ao criar lista de concatenação de música: {e}", "error"))
        return False

    cmd_concat = [
        params['ffmpeg_path'], '-y', '-f', 'concat', '-safe', '0', '-i', concat_list_path,
        '-c', 'aac', '-b:a', '192k', 
        output_path
    ]
    
    return _execute_ffmpeg(cmd_concat, 0, None, cancel_event, f"{log_prefix} (Música)", progress_queue)

def _wrap_text_to_width(text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    if max_width <= 0:
        return [text]

    dummy_img = Image.new('RGB', (10, 10))
    draw = ImageDraw.Draw(dummy_img)
    lines: List[str] = []
    paragraphs = text.split('\n') if text else ['']

    for paragraph in paragraphs:
        paragraph = paragraph or ''
        words = paragraph.split(' ')
        current_line = ''

        for raw_word in words:
            word = raw_word.strip()
            if not word:
                if current_line:
                    lines.append(current_line)
                    current_line = ''
                continue

            tentative = word if not current_line else f"{current_line} {word}"
            if draw.textlength(tentative, font=font) <= max_width:
                current_line = tentative
                continue

            if current_line:
                lines.append(current_line)
                current_line = ''

            if draw.textlength(word, font=font) <= max_width:
                current_line = word
                continue

            chunk = ''
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

        lines.append('')

    if lines and lines[-1] == '':
        lines.pop()

    return lines or ['']


def _generate_typing_audio(text: str, char_duration: float, hold_duration: float, output_path: str, sample_rate: int = 44100) -> float:
    amplitude = 0.35
    base_frequency = 1100.0
    tone_ratio = 0.65
    data = array('h')

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

    with wave.open(output_path, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(data.tobytes())

    return len(data) / float(sample_rate)


def _create_typing_intro_clip(
    text: str,
    resolution: Tuple[int, int],
    params: Dict[str, Any],
    temp_dir: str,
    progress_queue: Queue,
    cancel_event: threading.Event,
    log_prefix: str
) -> Optional[Dict[str, Any]]:

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
    font_candidates = []
    subtitle_style = params.get('subtitle_style') or {}
    subtitle_font_path = subtitle_style.get('font_file') if isinstance(subtitle_style, dict) else None
    if subtitle_font_path:
        font_candidates.append(subtitle_font_path)
    font_candidates.extend(["arial.ttf", "DejaVuSans.ttf"])

    font: ImageFont.ImageFont
    for candidate in font_candidates:
        if not candidate:
            continue
        try:
            font = ImageFont.truetype(candidate, font_size)
            break
        except (OSError, FileNotFoundError):
            continue
    else:
        font = ImageFont.load_default()

    max_text_width = int(width * 0.8)

    def render_frame_text(current_text: str) -> Image.Image:
        img = Image.new('RGB', (width, height), color=(0, 0, 0))
        draw = ImageDraw.Draw(img)
        lines = _wrap_text_to_width(current_text, font, max_text_width)
        line_heights: List[int] = []
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
            x_cursor = max(0, (width - line_width) // 2)
            if line:
                draw.text((x_cursor, y_cursor), line, font=font, fill=(255, 255, 255))
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
    _generate_typing_audio(text, char_duration, hold_duration, audio_path)

    intro_clip_path = os.path.join(intro_temp_dir, "typing_intro.mp4")
    frame_pattern = os.path.join(frames_dir, "frame_%05d.png")

    progress_queue.put(("status", f"[{log_prefix}] Gerando clipe de introdução digitada...", "info"))

    cmd_intro = [
        params['ffmpeg_path'], '-y',
        '-framerate', str(frame_rate),
        '-i', frame_pattern,
        '-i', audio_path,
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-shortest', intro_clip_path
    ]

    if not _execute_ffmpeg(cmd_intro, total_duration, None, cancel_event, f"{log_prefix} (Intro)", progress_queue):
        return None

    return {
        'path': intro_clip_path,
        'duration': total_duration,
    }


def _maybe_create_intro_clip(
    params: Dict[str, Any],
    temp_dir: str,
    resolution: Tuple[int, int],
    progress_queue: Queue,
    cancel_event: threading.Event,
    log_prefix: str
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
    log_prefix: str
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
    offset = max(0.0, intro_duration - fade_duration)

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

    def merge_progress(pct: float):
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


def _perform_final_pass(
    params: Dict, base_video_path: str, narration_path: Optional[str],
    music_paths: List[str], subtitle_path: Optional[str],
    progress_queue: Queue, cancel_event: threading.Event, temp_dir: str, log_prefix: str
) -> bool:
    
    if not base_video_path or not os.path.exists(base_video_path):
        progress_queue.put(("status", f"[{log_prefix}] Erro Interno: Arquivo de vídeo base não foi encontrado.", "error"))
        return False

    content_duration = 0
    narration_props = _probe_media_properties(narration_path, params['ffmpeg_path']) if narration_path and os.path.isfile(narration_path) else None
    if narration_props and 'format' in narration_props and 'duration' in narration_props['format']:
        content_duration = float(narration_props['format']['duration'])
    else:
        video_props = _probe_media_properties(base_video_path, params['ffmpeg_path'])
        if video_props and 'format' in video_props:
            content_duration = float(video_props['format']['duration'])
    if content_duration <= 0:
        progress_queue.put(("status", f"[{log_prefix}] AVISO: Não foi possível determinar a duração do conteúdo.", "warning"))
        content_duration = 1
    
    total_duration = content_duration or 0

    inputs = []
    filter_complex_parts = []
    map_args = []
    input_map = {}
    current_idx = 0

    inputs.extend(["-i", base_video_path]); input_map['main_video'] = current_idx; current_idx += 1
    last_video_stream = f"[{input_map['main_video']}:v]"

    if params.get('effect_overlay_path') and os.path.isfile(params['effect_overlay_path']):
        inputs.extend(["-stream_loop", "-1", "-i", params['effect_overlay_path']]); input_map['effect'] = current_idx; current_idx += 1
    if params.get('png_overlay_path') and os.path.isfile(params['png_overlay_path']):
        inputs.extend(["-i", params['png_overlay_path']]); input_map['png'] = current_idx; current_idx += 1
    if params.get('presenter_video_path') and os.path.isfile(params['presenter_video_path']):
        inputs.extend(["-stream_loop", "-1", "-i", params['presenter_video_path']]); input_map['presenter'] = current_idx; current_idx += 1

    if narration_path and os.path.isfile(narration_path):
        inputs.extend(["-i", narration_path]); input_map['narration'] = current_idx; current_idx += 1
    if music_paths and music_paths[0] and os.path.isfile(music_paths[0]):
        inputs.extend(["-i", music_paths[0]]); input_map['music'] = current_idx; current_idx += 1

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
            "info"
        ))

    filter_complex_parts.append(f"{last_video_stream}scale={W}:{H},setsar=1[v_scaled]")
    last_video_stream = "[v_scaled]"

    # --- EFFECT OVERLAY (com opacidade) ---
    if 'effect' in input_map:
        blend_mode = params.get('effect_blend_mode', 'screen').lower()
        effect_opacity = float(params.get('effect_blend_opacity', 0.25))  # 25% é seguro
        filter_complex_parts.append(f"[{input_map['effect']}:v]scale={W}:{H},format=rgba[effect_scaled]")
        filter_complex_parts.append(
            f"{last_video_stream}[effect_scaled]"
            f"blend=all_mode={blend_mode}:all_opacity={effect_opacity}[v_effect]"
        )
        last_video_stream = "[v_effect]"

    # --- PRESENTER (com chroma key) ---
    if 'presenter' in input_map:
        pos = params.get('presenter_position', 'Inferior Central')
        pos_x = {'Inferior Esquerdo': '10', 'Inferior Central': '(W-w)/2', 'Inferior Direito': 'W-w-10'}.get(pos, '(W-w)/2')
        scale = float(params.get('presenter_scale', 0.40))
        target_h = int(H * scale)
        position = f"{pos_x}:H-h"

        if params.get('presenter_chroma_enabled'):
            chroma_hex = params.get('presenter_chroma_color', '#00FF00').replace('#', '0x')
            
            # **INÍCIO DA CORREÇÃO**
            # Valores crus vindos da UI, com clamp e mapeamento para faixas seguras do FFmpeg
            raw_sim = float(params.get('presenter_chroma_similarity', 0.20))
            raw_smth = float(params.get('presenter_chroma_blend', 0.10))
            
            # Clamp 0..1 para garantir que os valores estão no intervalo esperado
            raw_sim = max(0.0, min(raw_sim, 1.0))
            raw_smth = max(0.0, min(raw_smth, 1.0))
            
            # Mapeia para faixas úteis do FFmpeg para evitar o "efeito fantasma"
            sim = 0.05 + 0.45 * raw_sim   # Mapeia [0, 1] para [0.05, 0.50]
            smth = 0.02 + 0.28 * raw_smth  # Mapeia [0, 1] para [0.02, 0.30]
            # **FIM DA CORREÇÃO**

            # gera alpha a partir do verde e só então faz overlay
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
        pos_map = {"Superior Esquerdo": "10:10", "Superior Direito": "W-w-10:10", "Inferior Esquerdo": "10:H-h-10", "Inferior Direito": "W-w-10:H-h-10"}
        position = pos_map.get(params.get('png_overlay_position'), "W-w-10:H-h-10")
        scale = params.get('png_overlay_scale', 0.15); opacity = params.get('png_overlay_opacity', 1.0)
        filter_complex_parts.append(f"[{input_map['png']}:v]format=rgba,colorchannelmixer=aa={opacity},scale=w='iw*{scale}':h=-1[png_scaled]")
        filter_complex_parts.append(f"{last_video_stream}[png_scaled]overlay={position}:format=auto[v_png]")
        last_video_stream = "[v_png]"

    if params.get('add_fade_out'):
        fade_duration = params.get('fade_out_duration', 10)
        fade_start_time = max(0, content_duration - fade_duration)
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
    last_audio_stream = None
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
        fade_duration = params.get('fade_out_duration', 10)
        fade_start_time = max(0, content_duration - fade_duration)
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
        # Tenta mapear o áudio do vídeo base se nenhum outro áudio for fornecido
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

    # Sempre força o encerramento assim que o insumo mais curto terminar.
    # Isso evita travamentos quando usamos streams infinitos (ex.: stream_loop -1)
    # para overlays e também quando o fade-out deixa o trecho final mais curto que
    # as faixas auxiliares.
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

    def final_progress_callback(pct):
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
        success = _execute_ffmpeg(cmd_final_attempt, total_duration, final_progress_callback, cancel_event, f"{log_prefix} (Final)", progress_queue)

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

def _run_batch_video_processing(params: Dict[str, Any], progress_queue: Queue, cancel_event: threading.Event, temp_dir: str) -> bool:
    if cancel_event.is_set(): return False
    
    audio_folder = params.get('batch_audio_folder')
    video_parent_folder = params.get('batch_video_parent_folder')
    srt_folder = params.get('batch_srt_folder')
    music_folder = params.get('music_folder_path')

    lang_code_to_folder_name_map = {
        "ALE": "Alemão", "BUL": "Búlgaro", "ESP": "Espanhol", "FRAN": "Francês", "GREGO": "Grego", 
        "HOLAND": "Holandês", "ING": "Inglês", "ITA": "Italiano", "POL": "Polonês", "PT": "Português", "ROM": "Romeno"
    }
    
    if not audio_folder or not os.path.isdir(audio_folder):
        progress_queue.put(("status", "Erro: Pasta de áudios do lote inválida.", "error")); return False
    if not video_parent_folder or not os.path.isdir(video_parent_folder):
        progress_queue.put(("status", "Erro: Pasta de vídeos do lote inválida.", "error")); return False

    audio_files = sorted([f for f in os.listdir(audio_folder) if os.path.isfile(os.path.join(audio_folder, f)) and f.lower().endswith(('.mp3', '.wav', '.aac'))])
    if not audio_files:
        progress_queue.put(("status", "Erro: Nenhum arquivo de áudio encontrado na pasta de lote.", "error")); return False
    
    available_music_files = []
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
        progress_queue.put(("status", f"Erro ao ler subpastas de vídeo: {e}", "error")); return False
        
    total_files = len(audio_files)
    for i, audio_filename in enumerate(audio_files):
        if cancel_event.is_set(): return False
        
        progress_queue.put(("batch_progress", (i) / total_files))
        log_prefix = f"Lote Vídeo {i+1}/{total_files}"
        progress_queue.put(("status", f"--- Iniciando {log_prefix}: {audio_filename} ---", "info"))
        
        try:
            parts = Path(audio_filename).stem.split()
            if len(parts) < 2: raise IndexError("Formato de nome de arquivo inválido.")
            lang_code = _normalize_language_code(parts[1]) or parts[1].upper()
            language_name = lang_code_to_folder_name_map.get(lang_code)
            if not language_name:
                 progress_queue.put(("status", f"[{log_prefix}] Aviso: Código '{lang_code}' não mapeado. Pulando.", "warning")); continue
        except IndexError:
            progress_queue.put(("status", f"[{log_prefix}] Aviso: Nome de áudio '{audio_filename}' inválido. Pulando.", "warning")); continue

        target_video_folder = next((os.path.join(video_parent_folder, d) for d in video_subfolders if d.lower().startswith(language_name.lower())), None)
        
        if not target_video_folder:
            progress_queue.put(("status", f"[{log_prefix}] Aviso: Pasta de vídeo para '{language_name}' não encontrada. Pulando.", "warning")); continue
            
        try:
            available_videos = sorted([os.path.join(target_video_folder, f) for f in os.listdir(target_video_folder) if f.lower().endswith(('.mp4', '.mov', '.mkv', '.avi'))])
        except OSError as e:
            progress_queue.put(("status", f"[{log_prefix}] Erro ao ler vídeos de '{target_video_folder}': {e}. Pulando.", "error")); continue

        if not available_videos:
            progress_queue.put(("status", f"[{log_prefix}] Aviso: Nenhum vídeo encontrado em '{target_video_folder}'. Pulando.", "warning")); continue

        subtitle_file = None
        if srt_folder and os.path.isdir(srt_folder):
            potential_srt = os.path.join(srt_folder, f"{Path(audio_filename).stem}.srt")
            if os.path.isfile(potential_srt): subtitle_file = potential_srt

        item_temp_dir = tempfile.mkdtemp(prefix=f"kyle-batch-vid-item-{i}-", dir=temp_dir)
        
        music_files_for_pass = []
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
        
        del final_pass_params
        gc.collect()

    progress_queue.put(("batch_progress", 1.0))
    return True


def _run_batch_image_processing(params: Dict[str, Any], progress_queue: Queue, cancel_event: threading.Event, temp_dir: str) -> bool:
    if cancel_event.is_set(): return False
    
    audio_folder = params.get('batch_audio_folder')
    image_folder = params.get('batch_image_parent_folder')
    srt_folder = params.get('batch_srt_folder')
    music_folder = params.get('music_folder_path')

    if not audio_folder or not os.path.isdir(audio_folder):
        progress_queue.put(("status", "Erro: Pasta de áudios do lote inválida.", "error")); return False
    if not image_folder or not os.path.isdir(image_folder):
        progress_queue.put(("status", "Erro: Pasta de imagens do lote inválida.", "error")); return False

    audio_files = sorted([f for f in os.listdir(audio_folder) if os.path.isfile(os.path.join(audio_folder, f)) and f.lower().endswith(('.mp3', '.wav', '.aac'))])
    if not audio_files:
        progress_queue.put(("status", "Erro: Nenhum arquivo de áudio encontrado na pasta de lote.", "error")); return False
    
    supported_ext = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
    all_images = [p for p in Path(image_folder).iterdir() if p.is_file() and p.suffix.lower() in supported_ext]
    if not all_images:
        progress_queue.put(("status", f"Erro: Nenhuma imagem encontrada na pasta de imagens selecionada: {image_folder}", "error"))
        return False

    available_music_files = []
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
        if cancel_event.is_set(): return False
        
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
            
        if cancel_event.is_set(): return False
        
        progress_queue.put(("status", f"[{log_prefix}] Adicionando áudios e legendas...", "info"))
        
        subtitle_file = None
        if srt_folder and os.path.isdir(srt_folder):
            potential_srt = os.path.join(srt_folder, f"{Path(audio_filename).stem}.srt")
            if os.path.isfile(potential_srt): subtitle_file = potential_srt
            
        music_files_for_pass = []
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
        
        del base_video_path, final_pass_params, images_for_this_video
        gc.collect() 

    progress_queue.put(("batch_progress", 1.0))
    return True

def _run_batch_mixed_processing(params: Dict[str, Any], progress_queue: Queue, cancel_event: threading.Event, temp_dir: str) -> bool:
    if cancel_event.is_set(): return False
    
    log_prefix_main = "Lote Misto"
    
    audio_folder = params.get('batch_audio_folder')
    mixed_media_folder = params.get('batch_mixed_media_folder')
    srt_folder = params.get('batch_srt_folder')
    music_folder = params.get('music_folder_path')

    if not audio_folder or not os.path.isdir(audio_folder):
        progress_queue.put(("status", f"[{log_prefix_main}] Erro: Pasta de áudios do lote inválida.", "error")); return False
    if not mixed_media_folder or not os.path.isdir(mixed_media_folder):
        progress_queue.put(("status", f"[{log_prefix_main}] Erro: Pasta de mídia (vídeos/imagens) inválida.", "error")); return False

    progress_queue.put(("status", f"[{log_prefix_main}] Analisando pasta de mídia para criar vídeo base...", "info"))
    all_files = list(Path(mixed_media_folder).iterdir())
    supported_img_ext = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
    supported_vid_ext = ('.mp4', '.mov', '.mkv', '.avi')
    images = sorted([p for p in all_files if p.is_file() and p.suffix.lower() in supported_img_ext])
    videos = sorted([p for p in all_files if p.is_file() and p.suffix.lower() in supported_vid_ext])
    
    if not images and not videos:
        progress_queue.put(("status", f"[{log_prefix_main}] Erro: Nenhuma imagem ou vídeo encontrado em {mixed_media_folder}", "error")); return False
    progress_queue.put(("status", f"[{log_prefix_main}] Encontrados {len(videos)} vídeos e {len(images)} imagens.", "info"))

    base_video_path = None
    base_video_creation_temp_dir = tempfile.mkdtemp(prefix="kyle-base-video-", dir=temp_dir)
    
    try:
        files_to_concat_ts = []
        w, h = _parse_resolution(params['resolution'])

        if videos:
            progress_queue.put(("status", f"[{log_prefix_main}] Padronizando vídeos para montagem...", "info"))
            for idx, video_path in enumerate(videos):
                if cancel_event.is_set(): raise InterruptedError()
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
            for path in files_to_concat_ts: f.write(f"file '{Path(path).as_posix()}'\n")

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
        progress_queue.put(("status", f"[{log_prefix_main}] Erro: Nenhum arquivo de áudio encontrado.", "error")); return False
    
    available_music_files = []
    if music_folder and os.path.isdir(music_folder):
        music_ext = ('.mp3', '.wav', '.aac', '.flac', '.ogg')
        available_music_files = [os.path.join(music_folder, f) for f in os.listdir(music_folder) if f.lower().endswith(music_ext)]

    total_files = len(audio_files)
    for i, audio_filename in enumerate(audio_files):
        if cancel_event.is_set(): break
        
        progress_queue.put(("batch_progress", (i) / total_files))
        log_prefix = f"Lote Misto {i+1}/{total_files}"
        progress_queue.put(("status", f"--- Iniciando {log_prefix}: {audio_filename} ---", "info"))
        
        narration_path = os.path.join(audio_folder, audio_filename)
        subtitle_file = None
        if srt_folder and os.path.isdir(srt_folder):
            potential_srt = os.path.join(srt_folder, f"{Path(audio_filename).stem}.srt")
            if os.path.isfile(potential_srt): subtitle_file = potential_srt
        
        item_temp_dir = tempfile.mkdtemp(prefix=f"kyle-mixed-item-{i}-", dir=temp_dir)

        music_files_for_pass = []
        if available_music_files:
            narration_props = _probe_media_properties(narration_path, params['ffmpeg_path'])
            target_duration = float(narration_props['format']['duration']) if narration_props else 0
            if params.get('add_fade_out'): target_duration += params.get('fade_out_duration', 10)
            
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
            params=final_pass_params, base_video_path=base_video_path, narration_path=narration_path,
            music_paths=music_files_for_pass, subtitle_path=subtitle_file,
            progress_queue=progress_queue, cancel_event=cancel_event,
            temp_dir=item_temp_dir, log_prefix=log_prefix
        )
        shutil.rmtree(item_temp_dir)
        gc.collect()

    shutil.rmtree(base_video_creation_temp_dir)
    progress_queue.put(("batch_progress", 1.0))
    return not cancel_event.is_set()


def _get_music_playlist(available_music: List[str], target_duration: float, params: Dict, ffmpeg_path: str) -> List[str]:
    """Cria uma lista de caminhos de música para atingir a duração desejada."""
    if not available_music:
        return []
    
    if params.get('batch_music_behavior') == 'loop':
        return [random.choice(available_music)]

    playlist = []
    current_duration = 0
    shuffled_music = random.sample(available_music, len(available_music))
    
    while current_duration < target_duration and target_duration > 0:
        if not shuffled_music:
            if not available_music: break
            shuffled_music = random.sample(available_music, len(available_music))
        
        music_path = shuffled_music.pop(0)
        props = _probe_media_properties(music_path, ffmpeg_path)
        if props and 'format' in props and 'duration' in props['format']:
            duration = float(props['format']['duration'])
            playlist.append(music_path)
            current_duration += duration
        
    if not playlist and available_music:
        playlist.append(random.choice(available_music))
        
    return playlist


def _run_hierarchical_batch_image_processing(params: Dict[str, Any], progress_queue: Queue, cancel_event: threading.Event, temp_dir: str) -> bool:
    if cancel_event.is_set(): return False

    root_folder = params.get('batch_root_folder')
    image_folder = params.get('batch_image_parent_folder')
    music_folder = params.get('music_folder_path')
    
    if not root_folder or not os.path.isdir(root_folder):
        progress_queue.put(("status", "Erro: Pasta Raiz do lote inválida.", "error")); return False
    if not image_folder or not os.path.isdir(image_folder):
        progress_queue.put(("status", "Erro: Pasta de imagens do lote inválida.", "error")); return False

    progress_queue.put(("status", f"Buscando arquivos de áudio em subpastas de '{Path(root_folder).name}'...", "info"))
    audio_files_to_process = []
    try:
        audio_ext = ('.mp3', '.wav', '.aac')
        for f in Path(root_folder).rglob('*'):
            if f.is_file() and f.suffix.lower() in audio_ext:
                audio_files_to_process.append(f)
        
        audio_files_to_process.sort()
    except OSError as e:
        progress_queue.put(("status", f"Erro ao buscar arquivos de áudio: {e}", "error")); return False

    if not audio_files_to_process:
        progress_queue.put(("status", "Erro: Nenhum arquivo de áudio encontrado nas subpastas.", "error")); return False
    progress_queue.put(("status", f"Encontrados {len(audio_files_to_process)} arquivos de áudio para processar.", "info"))

    supported_img_ext = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
    all_images = [p for p in Path(image_folder).iterdir() if p.is_file() and p.suffix.lower() in supported_img_ext]
    if not all_images:
        progress_queue.put(("status", f"Erro: Nenhuma imagem encontrada em {image_folder}", "error")); return False

    available_music_files = []
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
        if cancel_event.is_set(): return False

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

        if cancel_event.is_set(): return False
        
        music_files_for_pass = []
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

        del base_video_path, final_pass_params, images_for_this_video
        gc.collect()

    progress_queue.put(("batch_progress", 1.0))
    return True
