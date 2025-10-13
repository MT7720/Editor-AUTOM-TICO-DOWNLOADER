"""Shared resources used by both the GUI and processing layers."""

from .intro_fonts import (
    INTRO_FONT_CHOICES,
    INTRO_FONT_ENTRIES,
    INTRO_FONT_REGISTRY,
    get_intro_font_candidates,
    resolve_intro_font_candidate_path,
)

__all__ = [
    "INTRO_FONT_CHOICES",
    "INTRO_FONT_ENTRIES",
    "INTRO_FONT_REGISTRY",
    "get_intro_font_candidates",
    "resolve_intro_font_candidate_path",
]
