"""Utilities for creating highlight banner overlays."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

__all__ = [
    "BANNER_HEIGHT_RATIO",
    "BANNER_MIN_HEIGHT",
    "BannerRenderConfig",
    "BannerRenderResult",
    "compute_banner_height",
    "generate_banner_image",
]

BANNER_HEIGHT_RATIO = 0.18
BANNER_MIN_HEIGHT = 80
MIN_FONT_SIZE = 14


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


@dataclass
class BannerRenderResult:
    """Result returned after rendering a banner overlay."""

    image: Image.Image
    font_size: int
    line_count: int
    text_width: int
    text_height: int


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


def _load_font(
    font_path: Optional[str],
    banner_height: int,
    *,
    font_size: Optional[int] = None,
) -> Tuple[ImageFont.ImageFont, int]:
    """Load the truetype font with ``font_size`` or a size based on ``banner_height``."""

    resolved_size = font_size or max(18, int(round(banner_height * 0.45)))
    font_candidates = [font_path] if font_path else []
    font_candidates.append("DejaVuSans.ttf")

    for candidate in font_candidates:
        if not candidate:
            continue
        try:
            return ImageFont.truetype(candidate, resolved_size), resolved_size
        except Exception:
            continue

    return ImageFont.load_default(), resolved_size


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


def generate_banner_image(config: BannerRenderConfig) -> BannerRenderResult:
    """Render an RGBA banner image according to ``config`` and return metadata."""

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

    draw = ImageDraw.Draw(banner)

    font_rgb = _parse_hex_color(config.font_color, default=(255, 255, 255))
    max_text_width = width * 0.9
    target_font_size = max(18, int(round(banner_height * 0.45)))
    min_font_size = max(MIN_FONT_SIZE, int(round(banner_height * 0.2)))

    resolved_lines: List[str] = []
    line_heights: List[int] = []
    line_widths: List[int] = []
    line_spacing = 0
    font: ImageFont.ImageFont
    font_size = target_font_size

    for candidate_size in range(target_font_size, min_font_size - 1, -1):
        font, font_size = _load_font(config.font_path, banner_height, font_size=candidate_size)
        candidate_lines = _wrap_text(config.text, draw, font, max_text_width)
        if not candidate_lines:
            resolved_lines = []
            line_heights = []
            line_widths = []
            line_spacing = 0
            break

        candidate_heights: List[int] = []
        candidate_widths: List[int] = []
        for line in candidate_lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            candidate_heights.append(bbox[3] - bbox[1])
            candidate_widths.append(bbox[2] - bbox[0])

        spacing = max(4, int(round(font_size * 0.2)))
        total_text_height = sum(candidate_heights) + spacing * (len(candidate_lines) - 1)
        max_line_width = max(candidate_widths) if candidate_widths else 0

        if max_line_width <= max_text_width and total_text_height <= banner_height * 0.9:
            resolved_lines = candidate_lines
            line_heights = candidate_heights
            line_widths = candidate_widths
            line_spacing = spacing
            break

        if candidate_size == min_font_size:
            resolved_lines = candidate_lines
            line_heights = candidate_heights
            line_widths = candidate_widths
            line_spacing = spacing
            break

    text_height = 0
    text_width = 0
    if resolved_lines:
        total_text_height = sum(line_heights) + line_spacing * (len(resolved_lines) - 1)
        text_height = int(total_text_height)
        text_width = int(max(line_widths) if line_widths else 0)
        y = max(0, int(round((banner_height - total_text_height) / 2)))
        for idx, line in enumerate(resolved_lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            line_width = bbox[2] - bbox[0]
            x = max(0, int(round((width - line_width) / 2)))
            draw.text((x, y), line, font=font, fill=(*font_rgb, 255))
            y += line_heights[idx] + line_spacing

    return BannerRenderResult(
        image=banner,
        font_size=font_size,
        line_count=len(resolved_lines),
        text_width=int(text_width),
        text_height=int(text_height),
    )
