"""Utilidades relacionadas a idiomas para o processamento de vídeos."""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

try:  # pragma: no cover - dependência opcional
    from deep_translator import GoogleTranslator  # type: ignore
except Exception:  # pragma: no cover - dependência opcional
    GoogleTranslator = None  # type: ignore

logger = logging.getLogger(__name__)

__all__ = [
    "LANGUAGE_CODE_MAP",
    "LANGUAGE_ALIASES",
    "LANGUAGE_TRANSLATION_CODES",
    "LANGUAGE_NAME_TO_CODE",
    "strip_accents",
    "normalize_language_code",
    "infer_language_code_from_name",
    "infer_language_code_from_filename",
    "attempt_translate_text",
]

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


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


LANGUAGE_NAME_TO_CODE: Dict[str, str] = {
    strip_accents(name).upper(): code for code, name in LANGUAGE_CODE_MAP.items()
}


def _fallback_google_api_translate(text: str, translator_target: str) -> Optional[str]:
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

    translated_segments: List[str] = []
    for segment in payload[0] or []:
        if isinstance(segment, list) and segment:
            translated_segments.append(str(segment[0]))

    joined = "".join(translated_segments).strip()
    return joined or None


def attempt_translate_text(text: str, target_code: Optional[str]) -> Tuple[Optional[str], bool]:
    if not text or not target_code:
        return None, False

    translator_target = LANGUAGE_TRANSLATION_CODES.get(target_code)
    if not translator_target:
        return None, False

    cleaned_source = text.strip()

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


def normalize_language_code(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    candidate = strip_accents(str(value).strip()).upper()
    if not candidate:
        return None
    candidate = LANGUAGE_ALIASES.get(candidate, candidate)
    if candidate in LANGUAGE_CODE_MAP:
        return candidate
    if candidate in LANGUAGE_NAME_TO_CODE:
        return LANGUAGE_NAME_TO_CODE[candidate]
    return None


def infer_language_code_from_name(name: str) -> Optional[str]:
    tokens = re.split(r"[\s._-]+", name) if name else []
    for token in tokens:
        normalized = normalize_language_code(token)
        if normalized:
            return normalized
    return None


def infer_language_code_from_filename(filename: str) -> Optional[str]:
    if not filename:
        return None
    stem = Path(filename).stem
    tokens = re.split(r"[^A-Za-zÀ-ÖØ-öø-ÿ]+", stem)
    for token in reversed(tokens):
        normalized = normalize_language_code(token)
        if normalized:
            return normalized
    return None
