"""Canvas previews used throughout the GUI."""

from __future__ import annotations

import os
import tkinter as tk
from typing import Any, Dict, Optional, Tuple

from PIL import Image, ImageTk

from .constants import SUBTITLE_POSITIONS
from .utils import logger
from video_processing.banner import BannerRenderConfig, BannerRenderResult, generate_banner_image


class BannerPreview(tk.Canvas):
    def __init__(self, parent: tk.Misc, **kwargs: Any) -> None:
        super().__init__(parent, bg="#1a1a1a", **kwargs)
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
        self.create_rectangle(0, 0, canvas_w, canvas_h, fill="#1a1a1a", outline="")

        if not enabled:
            self._last_result = None
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
            self.create_text(
                canvas_w / 2,
                canvas_h / 2,
                text="Erro na pré-visualização",
                fill="#E57373",
                font=("Segoe UI", 12, "bold"),
            )
            return

        ratio = canvas_w / float(config.video_width)
        preview_height = max(1, int(round(banner_image.height * ratio)))
        preview_image = banner_image.resize((canvas_w, preview_height), Image.Resampling.LANCZOS)

        composed = Image.new("RGBA", (canvas_w, canvas_h), (26, 26, 26, 255))
        y_offset = max(0, (canvas_h - preview_height) // 2)
        composed.paste(preview_image, (0, y_offset), preview_image)

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
