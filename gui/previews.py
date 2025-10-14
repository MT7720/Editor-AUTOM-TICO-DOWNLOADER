"""Canvas previews used throughout the GUI."""

from __future__ import annotations

import os
import tkinter as tk
from typing import Any, Dict, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageTk

from .constants import SUBTITLE_POSITIONS
from .utils import logger
from video_processing.banner import BannerRenderConfig, generate_banner_image


class BannerPreview(tk.Canvas):
    def __init__(self, parent: tk.Misc, **kwargs: Any) -> None:
        super().__init__(parent, bg="#1a1a1a", **kwargs)
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._last_params: Dict[str, Any] = {}
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
        }

        canvas_w, canvas_h = max(1, self.winfo_width()), max(1, self.winfo_height())
        self.delete("all")

        def _vertical_gradient(
            size: Tuple[int, int], top: Tuple[int, int, int, int], bottom: Tuple[int, int, int, int]
        ) -> Image.Image:
            width, height = size
            gradient = Image.new("RGBA", (width, height))
            draw = ImageDraw.Draw(gradient)
            if height <= 1:
                draw.rectangle((0, 0, width, height), fill=top)
                return gradient
            for y in range(height):
                ratio = y / (height - 1)
                color = tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(4))
                draw.line([(0, y), (width, y)], fill=color)
            return gradient

        background = _vertical_gradient((canvas_w, canvas_h), (44, 44, 50, 255), (18, 18, 22, 255))

        highlight_mask = Image.new("L", (canvas_w, canvas_h), 0)
        highlight_draw = ImageDraw.Draw(highlight_mask)
        inset = max(12, min(canvas_w, canvas_h) // 3)
        highlight_draw.ellipse((-inset, -inset, canvas_w + inset, canvas_h + inset), fill=140)
        highlight_overlay = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 30))
        highlight_overlay.putalpha(highlight_mask)
        background = Image.alpha_composite(background, highlight_overlay)

        if not enabled:
            self._photo = ImageTk.PhotoImage(background)
            self.create_image(0, 0, image=self._photo, anchor="nw")
            self.create_text(
                canvas_w / 2,
                canvas_h / 2,
                text="Faixa desativada",
                fill="#BBBBBB",
                font=("Segoe UI", 12, "italic"),
            )
            return

        try:
            video_w, video_h = video_resolution
            config = BannerRenderConfig(
                text=text or "",
                video_width=max(1, int(video_w)),
                video_height=max(1, int(video_h)),
                use_gradient=use_gradient,
                solid_color=solid_color or "#333333",
                gradient_start=gradient_start or solid_color or "#333333",
                gradient_end=gradient_end or solid_color or "#333333",
                font_color=font_color or "#FFFFFF",
                font_path=font_path,
            )
            banner_image = generate_banner_image(config)
        except Exception as exc:
            logger.error("Erro ao gerar pré-visualização da faixa: %s", exc)
            self._photo = ImageTk.PhotoImage(background)
            self.create_image(0, 0, image=self._photo, anchor="nw")
            self.create_text(
                canvas_w / 2,
                canvas_h / 2,
                text="Erro na pré-visualização",
                fill="#E57373",
                font=("Segoe UI", 12, "bold"),
            )
            return

        scale_w = (canvas_w * 0.9) / max(1, config.video_width)
        scale_h = (canvas_h * 0.8) / max(1, config.video_height)
        scale = max(0.1, min(scale_w, scale_h))
        aspect_ratio = config.video_width / max(1, config.video_height)
        frame_width = int(config.video_width * scale)
        frame_height = int(config.video_height * scale)

        max_width = min(canvas_w, max(60, canvas_w - 20))
        max_height = min(canvas_h, max(60, canvas_h - 20))
        min_width = min(160, max_width)
        min_height = min(90, max_height)

        if frame_width > max_width:
            frame_width = max_width
            frame_height = int(frame_width / aspect_ratio)
        if frame_height > max_height:
            frame_height = max_height
            frame_width = int(frame_height * aspect_ratio)

        frame_width = max(min_width, min(frame_width, max_width))
        frame_height = max(min_height, min(frame_height, max_height))
        frame_x = max(0, (canvas_w - frame_width) // 2)
        frame_y = max(0, (canvas_h - frame_height) // 2)

        shadow_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        shadow_box = Image.new("RGBA", (frame_width, frame_height), (0, 0, 0, 140))
        shadow_offset = max(4, frame_height // 30)
        shadow_layer.paste(shadow_box, (frame_x, frame_y + shadow_offset))
        blur_radius = max(6, min(frame_width, frame_height) // 30)
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        background = Image.alpha_composite(background, shadow_layer)

        frame_image = Image.new("RGBA", (frame_width, frame_height), (0, 0, 0, 0))
        frame_draw = ImageDraw.Draw(frame_image)
        outer_radius = max(12, min(frame_width, frame_height) // 12)
        frame_draw.rounded_rectangle(
            (0, 0, frame_width, frame_height),
            radius=outer_radius,
            fill=(16, 16, 19, 255),
        )
        frame_draw.rounded_rectangle(
            (1, 1, frame_width - 2, frame_height - 2),
            radius=max(outer_radius - 1, 8),
            outline=(255, 255, 255, 32),
        )

        inner_margin = max(12, min(frame_width, frame_height) // 18)
        inner_radius = max(6, outer_radius - inner_margin // 2)
        video_w_px = frame_width - inner_margin * 2
        video_h_px = frame_height - inner_margin * 2

        if video_w_px <= 0 or video_h_px <= 0:
            self._photo = ImageTk.PhotoImage(background)
            self.create_image(0, 0, image=self._photo, anchor="nw")
            return

        video_area = _vertical_gradient((video_w_px, video_h_px), (38, 41, 52, 255), (14, 16, 22, 255))
        sheen = Image.new("RGBA", (video_w_px, video_h_px), (255, 255, 255, 0))
        sheen_draw = ImageDraw.Draw(sheen)
        sheen_draw.rectangle((0, 0, video_w_px, int(video_h_px * 0.35)), fill=(255, 255, 255, 35))
        sheen_draw.rectangle(
            (0, int(video_h_px * 0.75), video_w_px, video_h_px),
            fill=(0, 0, 0, 70),
        )
        video_area = Image.alpha_composite(video_area, sheen)

        video_mask = Image.new("L", (video_w_px, video_h_px), 0)
        mask_draw = ImageDraw.Draw(video_mask)
        mask_draw.rounded_rectangle(
            (0, 0, video_w_px, video_h_px),
            radius=inner_radius,
            fill=255,
        )
        video_area.putalpha(video_mask)
        frame_layer = Image.new("RGBA", (frame_width, frame_height), (0, 0, 0, 0))
        frame_layer.paste(video_area, (inner_margin, inner_margin), video_area)
        frame_draw.rounded_rectangle(
            (inner_margin, inner_margin, frame_width - inner_margin, frame_height - inner_margin),
            radius=inner_radius,
            outline=(255, 255, 255, 26),
            width=2,
        )

        banner_available_w = max(1, int(video_w_px * 0.92))
        banner_scale = min(banner_available_w / max(1, banner_image.width), 1.0)
        banner_target_w = max(1, int(banner_image.width * banner_scale))
        banner_target_h = max(1, int(banner_image.height * banner_scale))
        banner_preview = banner_image.resize((banner_target_w, banner_target_h), Image.Resampling.LANCZOS)
        banner_mask = Image.new("L", (banner_target_w, banner_target_h), 0)
        mask_draw = ImageDraw.Draw(banner_mask)
        mask_draw.rounded_rectangle(
            (0, 0, banner_target_w, banner_target_h),
            radius=max(6, banner_target_h // 3),
            fill=255,
        )
        banner_preview.putalpha(banner_mask)
        banner_x = inner_margin + (video_w_px - banner_target_w) // 2
        banner_y = inner_margin + video_h_px - banner_target_h - max(8, video_h_px // 25)
        banner_y = max(inner_margin, banner_y)
        frame_layer.paste(banner_preview, (banner_x, banner_y), banner_preview)
        frame_image = Image.alpha_composite(frame_image, frame_layer)

        frame_canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        frame_canvas.paste(frame_image, (frame_x, frame_y), frame_image)
        composed = Image.alpha_composite(background, frame_canvas)

        self._photo = ImageTk.PhotoImage(composed)
        self.create_image(0, 0, image=self._photo, anchor="nw")


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
