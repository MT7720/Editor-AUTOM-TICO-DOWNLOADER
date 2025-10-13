"""Predefined fonts available to the typing intro renderer."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, List

INTRO_FONT_ENTRIES: List[Dict[str, Iterable[str]]] = [
    {
        "name": "Automático",
        "regular": [],
        "bold": [],
    },
    {
        "name": "DejaVu Sans",
        "regular": ["DejaVuSans.ttf", "DejaVuSans-Regular.ttf"],
        "bold": ["DejaVuSans-Bold.ttf"],
    },
    {
        "name": "Arial",
        "regular": ["arial.ttf", "Arial.ttf"],
        "bold": ["arialbd.ttf", "Arial-Bold.ttf"],
    },
    {
        "name": "Liberation Sans",
        "regular": ["LiberationSans-Regular.ttf", "LiberationSans.ttf"],
        "bold": ["LiberationSans-Bold.ttf"],
    },
    {
        "name": "Roboto",
        "regular": ["Roboto-Regular.ttf", "Roboto.ttf"],
        "bold": ["Roboto-Bold.ttf"],
    },
    {
        "name": "Open Sans",
        "regular": ["OpenSans-Regular.ttf", "OpenSans.ttf"],
        "bold": ["OpenSans-Bold.ttf"],
    },
]
"""List of dictionaries describing intro font presets."""

INTRO_FONT_REGISTRY: Dict[str, Dict[str, Iterable[str]]] = {
    entry["name"]: {"regular": list(entry.get("regular", [])), "bold": list(entry.get("bold", []))}
    for entry in INTRO_FONT_ENTRIES
}
"""Mapping between display names and their candidate font files."""

INTRO_FONT_CHOICES: List[str] = [entry["name"] for entry in INTRO_FONT_ENTRIES]
"""Ordered list of font names exposed in the GUI combobox."""

_DEF_BASE_PATH = Path(__file__).resolve().parent
_REPO_ROOT = _DEF_BASE_PATH.parent


def resolve_intro_font_candidate_path(candidate: str) -> str:
    """Expand the given candidate to an absolute path when possible."""

    if not candidate:
        return candidate

    if os.path.isabs(candidate):
        return candidate

    potential_paths = [
        Path(candidate),
        _DEF_BASE_PATH / candidate,
        _REPO_ROOT / candidate,
        _REPO_ROOT / "fonts" / candidate,
        _REPO_ROOT / "processing" / "fonts" / candidate,
        _REPO_ROOT / "resources" / "fonts" / candidate,
    ]

    for path in potential_paths:
        if path.exists():
            return str(path.resolve())

    return candidate


def get_intro_font_candidates(choice: str, *, bold: bool = False) -> List[str]:
    """Return a prioritized list of font candidates for the given choice."""

    entry = INTRO_FONT_REGISTRY.get(choice or "")
    candidates: List[str] = []

    if entry:
        if bold:
            candidates.extend(str(resolve_intro_font_candidate_path(c)) for c in entry.get("bold", []))
        candidates.extend(str(resolve_intro_font_candidate_path(c)) for c in entry.get("regular", []))

    return candidates


__all__ = [
    "INTRO_FONT_CHOICES",
    "INTRO_FONT_ENTRIES",
    "INTRO_FONT_REGISTRY",
    "get_intro_font_candidates",
    "resolve_intro_font_candidate_path",
]
