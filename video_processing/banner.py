"""Utilities for creating highlight banner overlays."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

__all__ = [
    "BANNER_HEIGHT_RATIO",
    "BANNER_MIN_HEIGHT",
    "BannerRenderConfig",
    "compute_banner_height",
    "generate_banner_image",
]

BANNER_HEIGHT_RATIO = 0.18
BANNER_MIN_HEIGHT = 80


@dataclass
class BannerRenderConfig:
    """Configuration bundle used to render a banner overlay."""

    text: str
    video_width: int
    video_height: int
    use_gradient: bool
    solid_color: str
    gradient_start: str
    gradient_end: str
    font_color: str
    font_path: Optional[str] = None


def compute_banner_height(video_height: int) -> int:
    """Calculate the banner height based on the target video height."""

    if video_height <= 0:
        return BANNER_MIN_HEIGHT
    dynamic_height = int(round(video_height * BANNER_HEIGHT_RATIO))
    return max(BANNER_MIN_HEIGHT, dynamic_height)


def _parse_hex_color(value: str, *, default: Tuple[int, int, int]) -> Tuple[int, int, int]:
    value = (value or "").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        return default
    try:
        r = int(value[0:2], 16)
        g = int(value[2:4], 16)
        b = int(value[4:6], 16)
        return r, g, b
    except ValueError:
        return default


def _load_font(font_path: Optional[str], banner_height: int) -> ImageFont.ImageFont:
    font_size = max(18, int(round(banner_height * 0.45)))
    if font_path:
        try:
            return ImageFont.truetype(font_path, font_size)
        except Exception:
            pass
    try:
        return ImageFont.truetype("DejaVuSans.ttf", font_size)
    except Exception:
        return ImageFont.load_default()


def _wrap_text(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, max_width: float) -> List[str]:
    text = text.replace("\r", "").strip()
    if not text:
        return []
    lines: List[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current_words: List[str] = []
        for word in words:
            candidate_words = current_words + [word]
            candidate = " ".join(candidate_words)
            width = draw.textlength(candidate, font=font)
            if width <= max_width or not current_words:
                current_words.append(word)
            else:
                lines.append(" ".join(current_words))
                current_words = [word]
        if current_words:
            lines.append(" ".join(current_words))
    return lines


def _draw_gradient(width: int, height: int, start: Tuple[int, int, int], end: Tuple[int, int, int]) -> Image.Image:
    if height <= 1:
        return Image.new("RGBA", (width, max(1, height)), (*start, 255))
    gradient = Image.new("RGBA", (1, height))
    draw = ImageDraw.Draw(gradient)
    for y in range(height):
        ratio = y / (height - 1)
        r = int(round(start[0] + (end[0] - start[0]) * ratio))
        g = int(round(start[1] + (end[1] - start[1]) * ratio))
        b = int(round(start[2] + (end[2] - start[2]) * ratio))
        draw.point((0, y), fill=(r, g, b, 255))
    return gradient.resize((max(1, width), height))


def generate_banner_image(config: BannerRenderConfig) -> Image.Image:
    """Render an RGBA banner image according to ``config``."""

    banner_height = compute_banner_height(config.video_height)
    width = max(1, int(config.video_width))
    banner = Image.new("RGBA", (width, banner_height), (0, 0, 0, 0))

    solid_rgb = _parse_hex_color(config.solid_color, default=(35, 35, 35))
    gradient_start = _parse_hex_color(config.gradient_start, default=solid_rgb)
    gradient_end = _parse_hex_color(config.gradient_end, default=solid_rgb)

    if config.use_gradient:
        background = _draw_gradient(width, banner_height, gradient_start, gradient_end)
    else:
        background = Image.new("RGBA", (width, banner_height), (*solid_rgb, 255))

    banner.paste(background, (0, 0))

    font = _load_font(config.font_path, banner_height)
    draw = ImageDraw.Draw(banner)

    font_rgb = _parse_hex_color(config.font_color, default=(255, 255, 255))
    max_text_width = width * 0.9
    lines = _wrap_text(config.text, draw, font, max_text_width)

    if lines:
        line_heights: List[int] = []
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_heights.append(bbox[3] - bbox[1])
        line_spacing = max(4, int(round(sum(line_heights) * 0.05)))
        total_text_height = sum(line_heights) + line_spacing * (len(lines) - 1)
        y = max(0, (banner_height - total_text_height) // 2)
        for idx, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            line_width = bbox[2] - bbox[0]
            x = max(0, int(round((width - line_width) / 2)))
            draw.text((x, y), line, font=font, fill=(*font_rgb, 255))
            y += line_heights[idx] + line_spacing

    return banner
