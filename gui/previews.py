"""Canvas previews used throughout the GUI."""

from __future__ import annotations

import os
import tkinter as tk
from typing import Any, Dict, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageTk

from .constants import SUBTITLE_POSITIONS
from .utils import logger
from video_processing.banner import BannerRenderConfig, BannerRenderResult, generate_banner_image


class BannerPreview(tk.Canvas):
    def __init__(self, parent: tk.Misc, **kwargs: Any) -> None:
        super().__init__(parent, bg="#14161f", highlightthickness=0, bd=0, **kwargs)
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._last_params: Dict[str, Any] = {}
        self._last_result: Optional[BannerRenderResult] = None
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event: tk.Event[Any]) -> None:  # pragma: no cover - UI callback
        if self._last_params:
            try:
                self.update_preview(**self._last_params)
            except Exception as exc:  # pragma: no cover - defensive UI
                logger.error("Erro ao atualizar preview da faixa após redimensionamento: %s", exc)

    def update_preview(
        self,
        text: str,
        use_gradient: bool,
        solid_color: str,
        gradient_start: str,
        gradient_end: str,
        font_color: str,
        enabled: bool,
        video_resolution: Tuple[int, int],
        font_path: Optional[str] = None,
        outline_enabled: bool = False,
        outline_color: str = "#000000",
        outline_offset: float = 2.0,
        shadow_enabled: bool = False,
        shadow_color: str = "#000000",
        shadow_offset_x: float = 3.0,
        shadow_offset_y: float = 3.0,
    ) -> None:
        self._last_params = {
            'text': text,
            'use_gradient': use_gradient,
            'solid_color': solid_color,
            'gradient_start': gradient_start,
            'gradient_end': gradient_end,
            'font_color': font_color,
            'enabled': enabled,
            'video_resolution': video_resolution,
            'font_path': font_path,
            'outline_enabled': outline_enabled,
            'outline_color': outline_color,
            'outline_offset': outline_offset,
            'shadow_enabled': shadow_enabled,
            'shadow_color': shadow_color,
            'shadow_offset_x': shadow_offset_x,
            'shadow_offset_y': shadow_offset_y,
        }

        canvas_w, canvas_h = max(1, self.winfo_width()), max(1, self.winfo_height())
        self.delete("all")

        try:
            video_w, video_h = video_resolution
        except Exception:
            video_w, video_h = (1920, 1080)

        try:
            video_w = max(1, int(video_w))
            video_h = max(1, int(video_h))
        except (TypeError, ValueError):
            video_w, video_h = 1920, 1080

        if not enabled:
            self._last_result = None
            mock_image, frame_bbox = self._compose_mock_scene(
                (canvas_w, canvas_h), (video_w, video_h), None
            )
            self._photo = ImageTk.PhotoImage(mock_image)
            self.create_image(0, 0, image=self._photo, anchor="nw")
            self._draw_overlay_message(frame_bbox, "Faixa desativada", fill="#c0c4d2")
            return

        try:
            config = BannerRenderConfig(
                text=text or "",
                video_width=video_w,
                video_height=video_h,
                use_gradient=use_gradient,
                solid_color=solid_color or "#333333",
                gradient_start=gradient_start or solid_color or "#333333",
                gradient_end=gradient_end or solid_color or "#333333",
                font_color=font_color or "#FFFFFF",
                font_path=font_path,
                outline_enabled=outline_enabled,
                outline_color=outline_color or "#000000",
                outline_offset=outline_offset,
                shadow_enabled=shadow_enabled,
                shadow_color=shadow_color or "#000000",
                shadow_offset_x=shadow_offset_x,
                shadow_offset_y=shadow_offset_y,
            )
            result = generate_banner_image(config)
            self._last_result = result
            banner_image = result.image
        except Exception as exc:
            logger.error("Erro ao gerar pré-visualização da faixa: %s", exc)
            self._last_result = None
            mock_image, frame_bbox = self._compose_mock_scene(
                (canvas_w, canvas_h), (video_w, video_h), None
            )
            self._photo = ImageTk.PhotoImage(mock_image)
            self.create_image(0, 0, image=self._photo, anchor="nw")
            self._draw_overlay_message(frame_bbox, "Erro na pré-visualização", fill="#E57373")
            return

        composed, frame_bbox = self._compose_mock_scene(
            (canvas_w, canvas_h), (config.video_width, config.video_height), banner_image
        )

        self._photo = ImageTk.PhotoImage(composed)
        self.create_image(0, 0, image=self._photo, anchor="nw")

    def _compose_mock_scene(
        self,
        canvas_size: Tuple[int, int],
        video_size: Tuple[int, int],
        banner_image: Optional[Image.Image],
    ) -> Tuple[Image.Image, Tuple[int, int, int, int]]:
        canvas_w, canvas_h = canvas_size
        canvas_w = max(1, canvas_w)
        canvas_h = max(1, canvas_h)

        base = Image.new("RGBA", (canvas_w, canvas_h))

        # Dramatic vertical gradient background with a bluish hue
        gradient_column = Image.new("RGBA", (1, canvas_h))
        top_bg = (38, 52, 86)
        bottom_bg = (9, 11, 22)
        gradient_data = []
        for y in range(canvas_h):
            mix = y / max(1, canvas_h - 1)
            r = int(top_bg[0] * (1 - mix) + bottom_bg[0] * mix)
            g = int(top_bg[1] * (1 - mix) + bottom_bg[1] * mix)
            b = int(top_bg[2] * (1 - mix) + bottom_bg[2] * mix)
            gradient_data.append((r, g, b, 255))
        gradient_column.putdata(gradient_data)
        base = gradient_column.resize((canvas_w, canvas_h))

        # Add soft radial glows to give depth to the preview
        glow_overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_overlay)
        glow_draw.ellipse(
            (
                -int(canvas_w * 0.35),
                -int(canvas_h * 0.6),
                int(canvas_w * 0.75),
                int(canvas_h * 0.55),
            ),
            fill=(120, 170, 255, 90),
        )
        glow_draw.ellipse(
            (
                int(canvas_w * 0.25),
                int(canvas_h * 0.25),
                int(canvas_w * 1.2),
                int(canvas_h * 1.25),
            ),
            fill=(180, 110, 255, 70),
        )
        glow_overlay = glow_overlay.filter(ImageFilter.GaussianBlur(radius=120))
        base = Image.alpha_composite(base, glow_overlay)

        # Subtle vignette for focus
        vignette = Image.new("L", (canvas_w, canvas_h), 0)
        vignette_draw = ImageDraw.Draw(vignette)
        vignette_draw.ellipse(
            (
                -int(canvas_w * 0.25),
                -int(canvas_h * 0.35),
                int(canvas_w * 1.25),
                int(canvas_h * 1.35),
            ),
            fill=255,
        )
        vignette = vignette.filter(ImageFilter.GaussianBlur(radius=140))
        vignette_layer = Image.new("RGBA", (canvas_w, canvas_h), (10, 12, 18, 220))
        vignette_layer.putalpha(ImageChops.invert(vignette))
        base = Image.alpha_composite(base, vignette_layer)

        # Light strips suggesting studio lighting
        strips_overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        strips_draw = ImageDraw.Draw(strips_overlay)
        strip_height = max(6, canvas_h // 18)
        for i in range(5):
            y = int(canvas_h * 0.18) + i * int(strip_height * 1.8)
            strips_draw.rectangle(
                (int(-canvas_w * 0.1), y, int(canvas_w * 1.1), y + strip_height),
                fill=(255, 255, 255, max(12, 40 - i * 5)),
            )
        strips_overlay = strips_overlay.filter(ImageFilter.GaussianBlur(radius=25))
        base = Image.alpha_composite(base, strips_overlay)

        video_w, video_h = video_size
        if video_w <= 0:
            video_w = 16
        if video_h <= 0:
            video_h = 9
        aspect = video_w / float(video_h)

        margin = int(round(min(canvas_w, canvas_h) * 0.08))
        available_w = max(20, canvas_w - margin * 2)
        available_h = max(20, canvas_h - margin * 2)
        frame_width = available_w
        frame_height = int(round(frame_width / aspect))
        if frame_height > available_h:
            frame_height = available_h
            frame_width = int(round(frame_height * aspect))
        frame_width = max(32, frame_width)
        frame_height = max(18, frame_height)

        frame_x0 = (canvas_w - frame_width) // 2
        frame_y0 = (canvas_h - frame_height) // 2
        frame_bbox = (frame_x0, frame_y0, frame_x0 + frame_width, frame_y0 + frame_height)

        frame_gradient_column = Image.new("RGBA", (1, frame_height))
        frame_top = (60, 64, 92)
        frame_bottom = (20, 24, 36)
        frame_gradient_data = []
        for y in range(frame_height):
            mix = y / max(1, frame_height - 1)
            r = int(frame_top[0] * (1 - mix) + frame_bottom[0] * mix)
            g = int(frame_top[1] * (1 - mix) + frame_bottom[1] * mix)
            b = int(frame_top[2] * (1 - mix) + frame_bottom[2] * mix)
            frame_gradient_data.append((r, g, b, 245))
        frame_gradient_column.putdata(frame_gradient_data)
        frame_body = frame_gradient_column.resize((frame_width, frame_height))

        radius = max(12, int(round(min(frame_width, frame_height) * 0.08)))
        frame_mask = Image.new("L", (frame_width, frame_height), 0)
        mask_draw = ImageDraw.Draw(frame_mask)
        mask_draw.rounded_rectangle(
            (0, 0, frame_width - 1, frame_height - 1), fill=255, radius=radius
        )

        frame_surface = Image.new("RGBA", (frame_width, frame_height), (0, 0, 0, 0))
        frame_surface.paste(frame_body, mask=frame_mask)
        frame_draw = ImageDraw.Draw(frame_surface)
        frame_draw.rounded_rectangle(
            (0, 0, frame_width - 1, frame_height - 1),
            outline=(196, 210, 255, 120),
            width=3,
            radius=radius,
        )
        frame_draw.rounded_rectangle(
            (4, 4, frame_width - 5, frame_height - 5),
            outline=(20, 22, 35, 180),
            width=2,
            radius=max(6, radius - 6),
        )

        # Stylized "screen" with subtle gradient and spotlight
        screen_margin_x = max(12, int(frame_width * 0.07))
        screen_margin_y = max(12, int(frame_height * 0.1))
        screen_width = max(20, frame_width - screen_margin_x * 2)
        screen_height = max(20, frame_height - screen_margin_y * 2)
        screen = Image.new("RGBA", (screen_width, screen_height))
        screen_gradient_column = Image.new("RGBA", (1, screen_height))
        screen_top = (26, 29, 44)
        screen_bottom = (10, 11, 20)
        screen_gradient = []
        for y in range(screen_height):
            mix = y / max(1, screen_height - 1)
            r = int(screen_top[0] * (1 - mix) + screen_bottom[0] * mix)
            g = int(screen_top[1] * (1 - mix) + screen_bottom[1] * mix)
            b = int(screen_top[2] * (1 - mix) + screen_bottom[2] * mix)
            screen_gradient.append((r, g, b, 240))
        screen_gradient_column.putdata(screen_gradient)
        screen = screen_gradient_column.resize((screen_width, screen_height))

        screen_overlay = Image.new("RGBA", (screen_width, screen_height), (0, 0, 0, 0))
        screen_draw = ImageDraw.Draw(screen_overlay)
        screen_draw.ellipse(
            (
                -int(screen_width * 0.1),
                int(-screen_height * 0.35),
                int(screen_width * 1.2),
                int(screen_height * 0.7),
            ),
            fill=(180, 210, 255, 90),
        )
        screen_draw.rectangle(
            (0, int(screen_height * 0.6), screen_width, screen_height),
            fill=(8, 10, 18, 140),
        )
        screen_overlay = screen_overlay.filter(ImageFilter.GaussianBlur(radius=50))
        screen = Image.alpha_composite(screen, screen_overlay)

        frame_surface.paste(
            screen,
            (screen_margin_x, screen_margin_y),
        )

        highlight = Image.new("RGBA", (frame_width, frame_height), (0, 0, 0, 0))
        highlight_draw = ImageDraw.Draw(highlight)
        highlight_draw.rectangle(
            (0, 0, frame_width, int(frame_height * 0.18)), fill=(255, 255, 255, 55)
        )
        highlight = highlight.filter(ImageFilter.GaussianBlur(radius=22))
        frame_surface = Image.alpha_composite(frame_surface, highlight)

        # Elevated shadow for glass effect
        shadow = Image.new(
            "RGBA", (frame_width + 36, frame_height + 36), (0, 0, 0, 0)
        )
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle(
            (18, 20, frame_width + 18, frame_height + 20),
            fill=(0, 0, 0, 170),
            radius=radius + 6,
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=28))
        base.alpha_composite(shadow, (frame_x0 - 18, frame_y0 - 14))
        base.alpha_composite(frame_surface, (frame_x0, frame_y0))

        if banner_image is not None and banner_image.width > 0 and banner_image.height > 0:
            horizontal_padding = max(16, int(round(frame_width * 0.09)))
            right_padding = horizontal_padding
            vertical_padding = max(16, int(round(frame_height * 0.12)))
            bottom_padding = max(16, int(round(frame_height * 0.12)))

            max_banner_width = min(
                int(frame_width * 0.86),
                max(1, frame_width - horizontal_padding - right_padding),
            )
            max_banner_height = min(
                int(frame_height * 0.4),
                max(1, frame_height - vertical_padding - bottom_padding),
            )
            scale = min(
                max_banner_width / float(banner_image.width),
                max_banner_height / float(banner_image.height),
            )
            scale = max(scale, 0.01)
            banner_size = (
                max(1, int(round(banner_image.width * scale))),
                max(1, int(round(banner_image.height * scale))),
            )
            banner_preview = banner_image.resize(
                banner_size, Image.Resampling.LANCZOS
            )

            banner_radius = max(10, int(round(banner_size[1] * 0.3)))

            glow_pad_x = max(10, int(banner_size[0] * 0.15))
            glow_pad_y = max(10, int(banner_size[1] * 0.4))
            glow_rect = Image.new(
                "RGBA",
                (banner_size[0] + glow_pad_x * 2, banner_size[1] + glow_pad_y * 2),
                (0, 0, 0, 0),
            )
            glow_draw = ImageDraw.Draw(glow_rect)
            glow_draw.rounded_rectangle(
                (0, glow_pad_y // 2, glow_rect.width, glow_rect.height),
                fill=(90, 130, 255, 110),
                radius=banner_radius + glow_pad_y // 3,
            )
            glow_rect = glow_rect.filter(ImageFilter.GaussianBlur(radius=35))

            banner_shadow = Image.new(
                "RGBA",
                (banner_size[0] + 28, banner_size[1] + 28),
                (0, 0, 0, 0),
            )
            banner_shadow_draw = ImageDraw.Draw(banner_shadow)
            banner_shadow_draw.rounded_rectangle(
                (14, 14, banner_size[0] + 14, banner_size[1] + 14),
                fill=(0, 0, 0, 180),
                radius=banner_radius + 6,
            )
            banner_shadow = banner_shadow.filter(ImageFilter.GaussianBlur(radius=18))

            banner_x = frame_x0 + horizontal_padding
            banner_y = frame_y0 + vertical_padding

            base.alpha_composite(
                glow_rect,
                (
                    banner_x - glow_pad_x,
                    banner_y - glow_pad_y,
                ),
            )
            base.alpha_composite(
                banner_shadow,
                (
                    banner_x - 14,
                    banner_y - 6,
                ),
            )
            base.paste(banner_preview, (banner_x, banner_y), banner_preview)

        return base, frame_bbox

    def _draw_overlay_message(
        self, frame_bbox: Tuple[int, int, int, int], message: str, *, fill: str = "#c0c4d2"
    ) -> None:
        fx0, fy0, fx1, fy1 = frame_bbox
        center_x = (fx0 + fx1) / 2
        center_y = (fy0 + fy1) / 2
        self.create_text(
            center_x,
            center_y,
            text=message,
            fill=fill,
            font=("Segoe UI", 12, "italic"),
        )


class SubtitlePreview(tk.Canvas):
    def __init__(self, parent: tk.Misc, app_ref: Any, **kwargs: Any) -> None:
        super().__init__(parent, bg="#1a1a1a", **kwargs)
        self.app = app_ref
        self.text_id = self.create_text(0, 0, text="Subtitle Preview", fill="white", anchor="center")
        self.outline_ids = [
            self.create_text(0, 0, text="Subtitle Preview", fill="black", anchor="center")
            for _ in range(4)
        ]
        self.tag_lower(self.outline_ids)
        self.tag_raise(self.text_id)
        self.bind("<Configure>", self._on_resize)
        self._font = ("Arial", 28, "bold")

    def _on_resize(self, event: tk.Event[Any]) -> None:  # pragma: no cover - UI callback
        self.app.update_subtitle_preview_job()

    def update_preview(
        self,
        text: str = "Subtitle Preview",
        font_config: Optional[Any] = None,
        text_color: str = "#FFFFFF",
        outline_color: str = "#000000",
        position_key: str = "Inferior Central",
    ) -> None:
        if font_config:
            self._font = font_config
        self.itemconfig(self.text_id, text=text, font=self._font, fill=text_color)
        for i in range(4):
            self.itemconfig(self.outline_ids[i], text=text, font=self._font, fill=outline_color)
        width, height = self.winfo_width(), self.winfo_height()
        pos = SUBTITLE_POSITIONS.get(position_key, 2)
        if pos in [7, 8, 9]:
            rely = 0.15
        elif pos in [4, 5, 6]:
            rely = 0.5
        else:
            rely = 0.85
        if pos in [1, 4, 7]:
            relx, anchor = 0.05, "w"
        elif pos in [3, 6, 9]:
            relx, anchor = 0.95, "e"
        else:
            relx, anchor = 0.5, "center"
        x, y = width * relx, height * rely
        self.coords(self.text_id, x, y)
        self.itemconfig(self.text_id, anchor=anchor)
        offsets = [(-2, -2), (2, -2), (2, 2), (-2, 2)]
        for i, (dx, dy) in enumerate(offsets):
            self.coords(self.outline_ids[i], x + dx, y + dy)
            self.itemconfig(self.outline_ids[i], anchor=anchor)


class PngPreview(tk.Canvas):
    def __init__(self, parent: tk.Misc, **kwargs: Any) -> None:
        super().__init__(parent, bg="#333333", **kwargs)
        self.logo_tk: Optional[ImageTk.PhotoImage] = None
        self.logo_id: Optional[int] = None
        self.bind("<Configure>", self.on_resize)

    def on_resize(self, event: Optional[tk.Event[Any]] = None) -> None:  # pragma: no cover - UI callback
        self.update_preview()

    def update_preview(
        self,
        logo_path: Optional[str] = None,
        position_key: str = "Inferior Direito",
        scale: float = 0.15,
        opacity: float = 1.0,
    ) -> None:
        self.delete("all")
        canvas_w, canvas_h = self.winfo_width(), self.winfo_height()

        self.create_rectangle(0, 0, canvas_w, canvas_h, fill="#333333", outline="")

        if not logo_path or not os.path.exists(logo_path) or canvas_w < 50 or canvas_h < 50:
            self.create_text(
                canvas_w / 2,
                canvas_h / 2,
                text="Selecione um PNG",
                fill="white",
                font=("Arial", 12),
            )
            return

        try:
            with Image.open(logo_path) as img:
                img_rgba = img.convert("RGBA")
                if opacity < 1.0:
                    alpha = img_rgba.split()[-1]
                    alpha = alpha.point(lambda p: int(p * opacity))
                    img_rgba.putalpha(alpha)

                target_h = int(canvas_h * scale)
                ratio = target_h / img_rgba.height
                target_w = int(img_rgba.width * ratio)

                img_resized = img_rgba.resize((target_w, target_h), Image.Resampling.LANCZOS)
                self.logo_tk = ImageTk.PhotoImage(img_resized)

                pos_map = {
                    "Superior Esquerdo": (10, 10),
                    "Superior Direito": (canvas_w - target_w - 10, 10),
                    "Inferior Esquerdo": (10, canvas_h - target_h - 10),
                    "Inferior Direito": (canvas_w - target_w - 10, canvas_h - target_h - 10),
                }
                x, y = pos_map.get(position_key, (10, 10))

                self.logo_id = self.create_image(x, y, image=self.logo_tk, anchor="nw")
        except Exception as exc:  # pragma: no cover - defensive image processing
            logger.error("Erro ao carregar preview do PNG: %s", exc)
            self.create_text(
                canvas_w / 2,
                canvas_h / 2,
                text="Erro ao carregar imagem",
                fill="red",
                font=("Arial", 12),
            )


class PresenterPreview(tk.Canvas):
    def __init__(self, parent: tk.Misc, **kwargs: Any) -> None:
        super().__init__(parent, bg="#333333", **kwargs)
        self.presenter_tk: Optional[ImageTk.PhotoImage] = None
        self.presenter_id: Optional[int] = None
        self.bind("<Configure>", self.on_resize)
        self.current_image_path: Optional[str] = None
        self.current_settings: Dict[str, Any] = {}

    def on_resize(self, event: Optional[tk.Event[Any]] = None) -> None:  # pragma: no cover - UI callback
        self.update_preview(self.current_image_path, **self.current_settings)

    def update_preview(
        self,
        image_path: Optional[str] = None,
        position_key: str = "Inferior Central",
        scale: float = 0.40,
        is_enabled: bool = False,
        error_message: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        self.current_image_path = image_path
        self.current_settings = {
            "position_key": position_key,
            "scale": scale,
            "is_enabled": is_enabled,
            "error_message": error_message,
        }

        self.delete("all")
        canvas_w, canvas_h = self.winfo_width(), self.winfo_height()
        self.create_rectangle(0, 0, canvas_w, canvas_h, fill="#333333", outline="")

        if error_message:
            self.create_text(
                canvas_w / 2,
                canvas_h / 2,
                text=error_message,
                fill="#E57373",
                font=("Segoe UI", 12, "bold"),
                width=canvas_w - 20,
                justify="center",
            )
            return

        if not is_enabled or not image_path or not os.path.exists(image_path):
            text = "Aguardando imagem..." if is_enabled else "Selecione um vídeo de apresentador"
            self.create_text(canvas_w / 2, canvas_h / 2, text=text, fill="white", font=("Arial", 12))
            return

        try:
            with Image.open(image_path) as img:
                target_h = int(canvas_h * float(scale))
                ratio = target_h / img.height
                target_w = int(img.width * ratio)

                if target_w < 1 or target_h < 1:
                    return

                img_resized = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
                self.presenter_tk = ImageTk.PhotoImage(img_resized)

                pos_x_map = {
                    "Inferior Esquerdo": 10,
                    "Inferior Central": (canvas_w - target_w) / 2,
                    "Inferior Direito": canvas_w - target_w - 10,
                }
                x = pos_x_map.get(position_key, (canvas_w - target_w) / 2)
                y = canvas_h

                self.presenter_id = self.create_image(x, y, image=self.presenter_tk, anchor="sw")
        except Exception as exc:  # pragma: no cover - defensive image processing
            logger.error("Erro ao carregar preview do apresentador: %s", exc)
            self.create_text(
                canvas_w / 2,
                canvas_h / 2,
                text="Erro ao carregar frame",
                fill="red",
                font=("Arial", 12),
            )


__all__ = ["SubtitlePreview", "PngPreview", "PresenterPreview"]
