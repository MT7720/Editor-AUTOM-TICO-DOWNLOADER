"""Main GUI application module for the editor and downloader."""

from __future__ import annotations

import ctypes
import datetime
import hashlib
import json
import logging
import os
import platform
import queue
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
import ttkbootstrap as ttk
import yt_dlp
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import colorchooser, filedialog, scrolledtext
from tkinter import font as tkFont
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox
from ttkbootstrap.tooltip import ToolTip

import license_checker

try:
    import video_processing_logic  # type: ignore
except ImportError:  # pragma: no cover - fallback assignment
    video_processing_logic = None  # type: ignore[assignment]

from .config_manager import ConfigManager
from .constants import (
    APP_DATA_PATH,
    APP_NAME,
    DEFAULT_GEOMETRY,
    EFFECT_BLEND_MODES,
    ICON_FILE,
    LANGUAGE_CODE_MAP,
    OVERLAY_POSITIONS,
    PRESENTER_POSITIONS,
    RESOLUTIONS,
    SLIDESHOW_MOTIONS,
    SLIDESHOW_TRANSITIONS,
    SUBTITLE_POSITIONS,
    SUPPORTED_FONT_FT,
    SUPPORTED_IMAGE_FT,
    SUPPORTED_MUSIC_FT,
    SUPPORTED_NARRATION_FT,
    SUPPORTED_PNG_FT,
    SUPPORTED_PRESENTER_FT,
    SUPPORTED_SUBTITLE_FT,
    SUPPORTED_VIDEO_FT,
    INTRO_FONT_CHOICES,
)
from .ffmpeg_manager import FFmpegManager
from .initializers import initialize_state, initialize_variables
from .previews import BannerPreview, PngPreview, PresenterPreview, SubtitlePreview
from .utils import configure_file_logging, logger


class VideoEditorApp:
    LICENSE_CHECK_INTERVAL_MS = 5 * 1000
    LICENSE_CHECK_MAX_INTERVAL_MS = 60 * 1000
    LICENSE_CHECK_JITTER_FACTOR = 0.2

    def __init__(self, root: Optional[ttk.Window] = None, license_data=None):
        self._owns_root = root is None
        self.root = root or ttk.Window(themename="superhero")

        if self._owns_root:
            self.root.withdraw()

        self.root.title(APP_NAME)
        if platform.system() == "Windows":
            try:
                from ctypes import windll
                windll.shcore.SetProcessDpiAwareness(1)
            except Exception as e:
                print(f"Não foi possível definir a conscientização de DPI: {e}")

        try:
            self.root.iconbitmap(ICON_FILE)
        except tk.TclError:
            logger.warning(f"Não foi possível carregar o ícone: {ICON_FILE}")
        self.root.geometry(DEFAULT_GEOMETRY)
        self.root.minsize(1100, 800)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.log_file_path = configure_file_logging()
        logger.info("Iniciando aplicativo.")
        self.config = ConfigManager.load_config()
        if license_data is not None:
            self.license_data = license_data
        else:
            fingerprint = license_checker.get_machine_fingerprint()
            try:
                self.license_data = license_checker.load_license_data(fingerprint)
            except license_checker.LicenseTamperedError:
                Messagebox.show_warning(
                    "Licença inválida",
                    "Os dados de licença guardados foram adulterados e precisarão de reativação.",
                )
                self.license_data = None
        self._license_id = self._extract_license_id(self.license_data)
        self._license_fingerprint = None
        self._license_check_job = None
        self._license_check_failures = 0
        self._license_termination_initiated = False
        initialize_variables(self, self.config)
        initialize_state(self)
        self._create_widgets()
        self.root.after(100, self.post_init_setup)
        self._initialize_license_monitoring()

    def post_init_setup(self):
        # Inicialização do Editor
        self.find_ffmpeg_on_startup()
        self.update_ui_for_media_type()
        self.update_subtitle_preview_job()
        self.update_png_preview_job()
        self.update_banner_preview_job()
        self.on_presenter_settings_change()
        self.check_queue()

        # Inicialização do Downloader em background
        self._downloader_initialize_systems()

        logger.info("Configuração da UI concluída.")

    def _extract_license_id(self, data: Optional[dict]) -> Optional[str]:
        if not data:
            return None
        try:
            return data.get("data", {}).get("id")
        except AttributeError:
            return None

    def _initialize_license_monitoring(self) -> None:
        if not self._license_id:
            logger.debug("Nenhuma licença carregada; monitoramento contínuo desativado.")
            return
        try:
            self._license_fingerprint = license_checker.get_machine_fingerprint()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Não foi possível obter a impressão digital da máquina para revalidação.", exc_info=exc)
            self._license_fingerprint = None
        self._schedule_license_check(initial=True)

    def _license_check_delay_ms(self, *, initial: bool = False) -> int:
        if initial:
            return 0

        base = self.LICENSE_CHECK_INTERVAL_MS
        if self._license_check_failures > 0:
            base *= 2 ** self._license_check_failures

        delay = min(base, self.LICENSE_CHECK_MAX_INTERVAL_MS)
        jitter_range = int(delay * self.LICENSE_CHECK_JITTER_FACTOR)
        if jitter_range > 0:
            delay += random.randint(-jitter_range, jitter_range)

        return max(delay, self.LICENSE_CHECK_INTERVAL_MS // 2)

    def _schedule_license_check(self, *, initial: bool = False) -> None:
        delay = self._license_check_delay_ms(initial=initial)
        if self._license_check_job is not None:
            try:
                self.root.after_cancel(self._license_check_job)
            except Exception:
                pass
        logger.debug(
            "Agendando verificação de licença em %s segundos (tentativas falhas: %s).",
            delay / 1000,
            self._license_check_failures,
        )
        self._license_check_job = self.root.after(delay, self._run_license_check)

    def _run_license_check(self) -> None:
        self._license_check_job = None
        if not self._license_id or self._license_termination_initiated:
            return
        fingerprint = self._license_fingerprint or license_checker.get_machine_fingerprint()
        license_key = None
        if isinstance(self.license_data, dict):
            license_key = self.license_data.get("meta", {}).get("key")

        payload = None
        error = None
        try:
            payload, error, invalidated = license_checker.validate_license_with_id(
                self._license_id, fingerprint, license_key
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Erro inesperado ao contactar o servidor de licenças.", exc_info=exc)
            error = str(exc)
            invalidated = False

        if invalidated:
            detail = None
            if isinstance(payload, dict):
                detail = payload.get("meta", {}).get("detail")
            detail = detail or "Licença não encontrada ou removida."
            logger.error("Licença inválida detectada: %s", detail)
            self._handle_invalid_license(detail)
            return

        if error or not payload:
            self._license_check_failures += 1
            logger.warning(
                "Não foi possível validar a licença. Tentativas falhas: %s. Nova tentativa em %s segundos.",
                self._license_check_failures,
                self._license_check_delay_ms(initial=False) / 1000,
            )
            if error:
                logger.debug("Motivo da falha na validação da licença: %s", error)
            self._schedule_license_check()
            return

        if payload.get("meta", {}).get("valid"):
            if self._license_check_failures:
                logger.info("Conectividade restabelecida. Licença validada novamente com o servidor.")
            self._license_check_failures = 0
            self._schedule_license_check()
            return

        detail = payload.get("meta", {}).get("detail") or "A licença está expirada ou inválida."
        logger.error("Licença inválida detectada: %s", detail)
        self._handle_invalid_license(detail)

    def _handle_invalid_license(self, detail: str) -> None:
        if self._license_termination_initiated:
            return
        self._license_termination_initiated = True
        Messagebox.show_warning(detail, "Licença inválida", parent=self.root)
        try:
            self.root.destroy()
        finally:
            sys.exit(1)

    def _create_widgets(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        self._create_files_tab()
        self._create_video_tab()
        self._create_banner_tab()
        self._create_audio_tab()
        self._create_intro_tab()
        self._create_effects_tab()
        self._create_subtitle_tab()
        self._create_overlay_tab()
        self._create_downloader_tab()
        self._create_settings_tab()
        self._create_status_bar()
    
    def on_tab_changed(self, event=None):
        try:
            current_tab_text = self.notebook.tab(self.notebook.select(), "text")
            logger.debug(f"Aba alterada para: {current_tab_text}")
            if "Sobreposições" in current_tab_text:
                logger.info("Aba 'Sobreposições' selecionada, atualizando as pré-visualizações.")
                self.update_png_preview_job()
                self.on_presenter_settings_change()
            elif "Downloader" in current_tab_text:
                 logger.info("Aba 'Downloader' selecionada.")
        except Exception as e:
            logger.warning(f"Erro ao lidar com a mudança de aba: {e}")

    # --- MÉTODO DE CRIAÇÃO DA ABA DE FICHEIROS (CORRIGIDO) ---
    def _create_files_tab(self):
        tab = ttk.Frame(self.notebook, padding=(20, 15))
        self.notebook.add(tab, text=" Editor: Ficheiros ")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(5, weight=1) # A linha do log irá expandir

        # --- Modo de Operação ---
        mode_section = ttk.LabelFrame(tab, text=" Modo de Operação ", padding=15)
        mode_section.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        mode_container = ttk.Frame(mode_section)
        mode_container.grid(row=0, column=0, sticky="ew")
        mode_container.columnconfigure(0, weight=1)

        mode_options = [
            (
                "Vídeo Único",
                "video_single",
                "Processa um único vídeo com possibilidade de adicionar narração e legendas personalizadas.",
            ),
            (
                "Slideshow Único",
                "image_folder",
                "Constrói um slideshow elegante a partir de uma pasta de imagens seleccionada, com transições configuráveis.",
            ),
            (
                "Lote de Vídeos",
                "batch_video",
                "Processa vários vídeos em sequência, reutilizando narrações e legendas partilhadas quando disponíveis.",
            ),
            (
                "Lote de Imagens",
                "batch_image",
                "Gera múltiplos slideshows automaticamente, ideal para colecções de imagens organizadas por pasta.",
            ),
            (
                "Lote Misto",
                "batch_mixed",
                "Combina vídeos e imagens num único lote de produção, garantindo alinhamento entre áudio e visuais.",
            ),
            (
                "Lote por Pasta Raiz",
                "batch_image_hierarchical",
                "Percorre subpastas numeradas dentro de uma pasta raiz e cria um vídeo independente para cada uma.",
            ),
        ]

        self._mode_descriptions: Dict[str, str] = {}
        self._mode_labels: Dict[str, str] = {}
        self._mode_buttons: Dict[str, ttk.Radiobutton] = {}

        buttons_frame = ttk.Frame(mode_container)
        buttons_frame.grid(row=0, column=0, sticky="ew")

        for index, (text, value, tip) in enumerate(mode_options):
            self._add_mode_option(
                container=buttons_frame,
                text=text,
                value=value,
                description=tip,
                position=index,
            )

        if not hasattr(self.media_type, "_mode_buttons_trace"):
            self.media_type._mode_buttons_trace = self.media_type.trace_add(
                "write", lambda *_: self._refresh_mode_cards()
            )
        self._refresh_mode_cards()

        # --- Ficheiros de Entrada ---
        input_section = ttk.LabelFrame(tab, text=" Ficheiros de Entrada ", padding=15)
        input_section.grid(row=1, column=0, sticky="ew", pady=(0, 15))
        input_section.columnconfigure(0, weight=1)
        
        inputs_container = ttk.Frame(input_section)
        inputs_container.grid(row=0, column=0, sticky="ew")
        inputs_container.columnconfigure(0, weight=1)

        self.single_inputs_frame = ttk.Frame(inputs_container); self.single_inputs_frame.grid(row=0, column=0, sticky="ew"); self.single_inputs_frame.columnconfigure(0, weight=1)
        self.media_path_label_widget = self._create_file_input(
            self.single_inputs_frame,
            0,
            "Arquivo de Vídeo Base (Obrigatório):",
            'media_single',
            self.select_media_single,
            hint_text=None,
        )
        self._create_file_input(
            self.single_inputs_frame,
            1,
            "Arquivo de Narração (Áudio) (Opcional):",
            'narration_single',
            lambda: self.select_file('narration_single', "Selecione o Arquivo de Narração (Áudio)", SUPPORTED_NARRATION_FT),
            hint_text=None,
        )
        self._create_file_input(
            self.single_inputs_frame,
            2,
            "Arquivo de Legenda (SRT) (Opcional):",
            'subtitle_single',
            lambda: self.select_file('subtitle_single', "Selecione o Arquivo de Legenda (SRT)", SUPPORTED_SUBTITLE_FT),
            hint_text=None,
        )

        self.batch_inputs_frame = ttk.Frame(inputs_container); self.batch_inputs_frame.grid(row=0, column=0, sticky="ew"); self.batch_inputs_frame.columnconfigure(0, weight=1)

        self.batch_video_inputs_frame = ttk.Frame(self.batch_inputs_frame); self.batch_video_inputs_frame.grid(row=0, column=0, sticky="ew"); self.batch_video_inputs_frame.columnconfigure(0, weight=1)
        self._create_file_input(
            self.batch_video_inputs_frame,
            0,
            "Pasta de Vídeos Base:",
            'batch_video',
            lambda: self.select_folder('batch_video', "Selecione a Pasta de Vídeos Base"),
            hint_text="⚠️ Necessária para processar cada vídeo do lote.",
        )
        self._create_file_input(
            self.batch_video_inputs_frame,
            1,
            "Pasta de Narrações (Áudio):",
            'batch_audio',
            lambda: self.select_folder('batch_audio', "Selecione a Pasta de Narrações (Áudio)"),
            hint_text="ℹ️ Usada por todos os vídeos; forneça apenas se quiser narrar.",
        )
        self._create_file_input(
            self.batch_video_inputs_frame,
            2,
            "Pasta de Legendas (SRT):",
            'batch_srt',
            lambda: self.select_folder('batch_srt', "Selecione a Pasta de Legendas (SRT)"),
            hint_text="ℹ️ Usada por todos os vídeos; importe apenas se já tiver legendas prontas.",
        )

        self.batch_image_inputs_frame = ttk.Frame(self.batch_inputs_frame); self.batch_image_inputs_frame.grid(row=0, column=0, sticky="ew"); self.batch_image_inputs_frame.columnconfigure(0, weight=1)
        self._create_file_input(
            self.batch_image_inputs_frame,
            0,
            "Pasta de Imagens Base:",
            'batch_image',
            lambda: self.select_folder('batch_image', "Selecione a Pasta de Imagens Base"),
            hint_text="⚠️ Necessária para montar cada vídeo do lote a partir das imagens.",
        )
        self._create_file_input(
            self.batch_image_inputs_frame,
            1,
            "Pasta de Narrações (Áudio):",
            'batch_audio',
            lambda: self.select_folder('batch_audio', "Selecione a Pasta de Narrações (Áudio)"),
            hint_text="ℹ️ Usada por todos os vídeos; forneça apenas se quiser narrar.",
        )
        self._create_file_input(
            self.batch_image_inputs_frame,
            2,
            "Pasta de Legendas (SRT):",
            'batch_srt',
            lambda: self.select_folder('batch_srt', "Selecione a Pasta de Legendas (SRT)"),
            hint_text="ℹ️ Usada por todos os vídeos; importe apenas se já tiver legendas prontas.",
        )

        self.batch_mixed_inputs_frame = ttk.Frame(self.batch_inputs_frame); self.batch_mixed_inputs_frame.grid(row=0, column=0, sticky="ew"); self.batch_mixed_inputs_frame.columnconfigure(0, weight=1)
        self._create_file_input(
            self.batch_mixed_inputs_frame,
            0,
            "Pasta de Mídia Base (Vídeos/Imagens):",
            'batch_mixed_media_folder',
            lambda: self.select_folder('batch_mixed_media_folder', "Selecione a Pasta de Mídia Base (Vídeos/Imagens)"),
            hint_text="⚠️ Necessária para processar cada mídia do lote (vídeos ou imagens).",
        )
        self._create_file_input(
            self.batch_mixed_inputs_frame,
            1,
            "Pasta de Narrações (Áudio):",
            'batch_audio',
            lambda: self.select_folder('batch_audio', "Selecione a Pasta de Narrações (Áudio)"),
            hint_text="ℹ️ Usada por todos os vídeos; forneça apenas se quiser narrar.",
        )
        self._create_file_input(
            self.batch_mixed_inputs_frame,
            2,
            "Pasta de Legendas (SRT):",
            'batch_srt',
            lambda: self.select_folder('batch_srt', "Selecione a Pasta de Legendas (SRT)"),
            hint_text="ℹ️ Usada por todos os vídeos; importe apenas se já tiver legendas prontas.",
        )

        self.batch_hierarchical_inputs_frame = ttk.Frame(self.batch_inputs_frame); self.batch_hierarchical_inputs_frame.grid(row=0, column=0, sticky="ew"); self.batch_hierarchical_inputs_frame.columnconfigure(0, weight=1)
        self._create_file_input(
            self.batch_hierarchical_inputs_frame,
            0,
            "Pasta Raiz do Lote:",
            'batch_root',
            lambda: self.select_folder('batch_root', "Selecione a Pasta Raiz do Lote com as subpastas numéricas"),
            hint_text="⚠️ Necessária: cada subpasta numerada vira um vídeo independente.",
        )
        self._create_file_input(
            self.batch_hierarchical_inputs_frame,
            1,
            "Biblioteca de Vídeos/Imagens:",
            'batch_image',
            lambda: self.select_folder('batch_image', "Selecione a Biblioteca de Vídeos/Imagens (Compartilhada)"),
            hint_text="ℹ️ Biblioteca compartilhada para todos os vídeos; as legendas são buscadas automaticamente.",
        )
        
        # --- Pasta de Saída (RESTAURADA) ---
        output_section = ttk.LabelFrame(tab, text=" Local de Saída ", padding=15)
        output_section.grid(row=2, column=0, sticky="ew", pady=(0, 15))
        output_section.columnconfigure(0, weight=1)
        self._create_file_input(output_section, 0, "Salvar em:", 'output', lambda: self.select_folder('output', "Selecione a Pasta de Saída"), hint_text=None)

        # --- Música de Fundo ---
        music_section = ttk.LabelFrame(tab, text=" Música de Fundo (Opcional) ", padding=15)
        music_section.grid(row=3, column=0, sticky="ew", pady=(0, 15))
        music_section.columnconfigure(0, weight=1)
        self.music_file_frame = self._create_file_input(music_section, 0, "Ficheiro de Música:", 'music_single', lambda: self.select_file('music_single', "Selecione a Música", SUPPORTED_MUSIC_FT), hint_text=None)
        self.music_folder_frame = ttk.Frame(music_section); self.music_folder_frame.grid(row=0, column=0, sticky="ew"); self.music_folder_frame.columnconfigure(0, weight=1)
        self._create_file_input(self.music_folder_frame, 0, "Pasta de Músicas:", 'music_folder', lambda: self.select_folder('music_folder', "Selecione a Pasta de Músicas"), hint_text=None)
        
        self.music_behavior_frame = ttk.Frame(self.music_folder_frame)
        self.music_behavior_frame.grid(row=1, column=0, sticky='ew', pady=(10,0))
        self.music_behavior_frame.columnconfigure(0, weight=1)
        behavior_label = ttk.Label(self.music_behavior_frame, text="Comportamento:", width=20, anchor='w')
        behavior_label.grid(row=0, column=0, sticky="w", padx=(0, 10))
        
        radio_container = ttk.Frame(self.music_behavior_frame)
        radio_container.grid(row=0, column=1, sticky='ew', columnspan=2)
        
        rb1 = ttk.Radiobutton(radio_container, text="Repetir (Loop)", variable=self.batch_music_behavior_var, value="loop")
        rb1.pack(side=LEFT, padx=(0, 15))
        ToolTip(rb1, "Uma única música aleatória será escolhida e repetida se for mais curta que o vídeo.")
        
        rb2 = ttk.Radiobutton(radio_container, text="Aleatório por Vídeo", variable=self.batch_music_behavior_var, value="random")
        rb2.pack(side=LEFT, padx=(0, 15))
        ToolTip(rb2, "Uma nova música aleatória da pasta será selecionada para cada vídeo no lote. Se a narração for longa, várias músicas serão usadas em sequência.")

        # --- Ações e Progresso (Grid row atualizado) ---
        self._create_editor_process_section(tab, 4)

    def _add_mode_option(
        self,
        *,
        container: ttk.Frame,
        text: str,
        value: str,
        description: str,
        position: int,
    ) -> None:
        self._mode_descriptions[value] = description
        self._mode_labels[value] = text
        button = ttk.Radiobutton(
            container,
            text=text,
            value=value,
            variable=self.media_type,
            command=self._on_mode_option_selected,
            bootstyle="outline-toolbutton",
        )
        button.pack(side=LEFT, padx=(0 if position == 0 else 10, 0))
        ToolTip(button, description)
        self._mode_buttons[value] = button

    def _on_mode_option_selected(self):
        self.update_ui_for_media_type()
        self._refresh_mode_cards()

    def _refresh_mode_cards(self):
        current_mode = self.media_type.get()
        if current_mode not in self._mode_buttons and self._mode_buttons:
            fallback_value = next(iter(self._mode_buttons))
            if fallback_value != current_mode:
                self.media_type.set(fallback_value)
                current_mode = fallback_value

        for value, button in self._mode_buttons.items():
            try:
                style = "primary-toolbutton" if value == current_mode else "outline-toolbutton"
                button.configure(bootstyle=style)
            except tk.TclError:
                pass

    def _on_single_language_selected(self, event=None):
        display_value = self.single_language_display_var.get()
        self.single_language_code_var.set(self.language_display_to_code.get(display_value, 'auto'))

    def _create_video_tab(self):
        # ... (sem alterações) ...
        tab = ttk.Frame(self.notebook, padding=(20, 15))
        self.notebook.add(tab, text=" Editor: Vídeo ")
        tab.columnconfigure(0, weight=1)

        self.video_settings_section = ttk.LabelFrame(tab, text=" Configurações Gerais de Vídeo ", padding=15)
        self.video_settings_section.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        self.video_settings_section.columnconfigure(1, weight=1)
        ttk.Label(self.video_settings_section, text="Resolução:").grid(row=0, column=0, sticky="w", padx=(0,10), pady=5)
        ttk.Combobox(self.video_settings_section, textvariable=self.resolution_var, values=RESOLUTIONS, state="readonly").grid(row=0, column=1, sticky="ew")
        ttk.Label(self.video_settings_section, text="Codificador:").grid(row=1, column=0, sticky="w", padx=(0,10), pady=5)
        self.video_codec_combobox = ttk.Combobox(self.video_settings_section, textvariable=self.video_codec_var, state="readonly")
        self.video_codec_combobox.grid(row=1, column=1, sticky="ew")

        self.slideshow_section = ttk.LabelFrame(tab, text=" Configurações de Slideshow ", padding=15)
        self.slideshow_section.grid(row=1, column=0, sticky="ew")
        self.slideshow_section.columnconfigure(1, weight=1)
        
        ttk.Label(self.slideshow_section, text="Duração por Imagem (s):").grid(row=0, column=0, sticky="w", padx=(0,10), pady=5)
        duration_frame = ttk.Frame(self.slideshow_section); duration_frame.grid(row=0, column=1, sticky="ew"); duration_frame.columnconfigure(0, weight=1)
        ttk.Scale(duration_frame, from_=1, to=30, variable=self.image_duration_var, orient=HORIZONTAL, command=lambda v: self.image_duration_var.set(int(float(v)))).grid(row=0, column=0, sticky="ew", padx=(0,10))
        ttk.Label(duration_frame, textvariable=self.image_duration_var, width=3).grid(row=0, column=1)
        
        ttk.Label(self.slideshow_section, text="Transição:").grid(row=1, column=0, sticky="w", padx=(0,10), pady=5)
        ttk.Combobox(self.slideshow_section, textvariable=self.transition_name_var, values=list(SLIDESHOW_TRANSITIONS.keys()), state="readonly").grid(row=1, column=1, sticky="ew")

        ttk.Label(self.slideshow_section, text="Duração da Transição (s):").grid(row=2, column=0, sticky="w", padx=(0,10), pady=5)
        trans_duration_frame = ttk.Frame(self.slideshow_section); trans_duration_frame.grid(row=2, column=1, sticky="ew"); trans_duration_frame.columnconfigure(0, weight=1)
        ttk.Scale(trans_duration_frame, from_=0.1, to=5.0, variable=self.transition_duration_var, orient=HORIZONTAL, command=lambda v: self.transition_duration_var.set(round(float(v),1))).grid(row=0, column=0, sticky="ew", padx=(0,10))
        ttk.Label(trans_duration_frame, textvariable=self.transition_duration_var, width=4).grid(row=0, column=1)

        ttk.Label(self.slideshow_section, text="Efeito de Movimento:").grid(row=3, column=0, sticky="w", padx=(0,10), pady=5)
        ttk.Combobox(self.slideshow_section, textvariable=self.motion_var, values=SLIDESHOW_MOTIONS, state="readonly").grid(row=3, column=1, sticky="ew")

        fade_out_section = ttk.LabelFrame(tab, text=" Encerramento (Fade Out) ", padding=15)
        fade_out_section.grid(row=2, column=0, sticky="ew", pady=(20, 0))
        fade_out_section.columnconfigure(1, weight=1)

        cb = ttk.Checkbutton(
            fade_out_section,
            text="Adicionar tela preta com fade out de áudio no final",
            variable=self.add_fade_out_var,
            bootstyle="round-toggle"
        )
        cb.grid(row=0, column=0, columnspan=2, sticky="w", pady=5)
        ToolTip(cb, "Adiciona um final suave ao vídeo, escurecendo a tela e silenciando o áudio.")

        ttk.Label(fade_out_section, text="Duração do Encerramento (s):").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=5)
        fade_duration_frame = ttk.Frame(fade_out_section)
        fade_duration_frame.grid(row=1, column=1, sticky="ew")
        fade_duration_frame.columnconfigure(0, weight=1)

        ttk.Scale(
            fade_duration_frame,
            from_=1,
            to=20,
            variable=self.fade_out_duration_var,
            orient=HORIZONTAL,
            command=lambda v: self.fade_out_duration_var.set(int(float(v)))
        ).grid(row=0, column=0, sticky="ew", padx=(0, 10))
        ttk.Label(fade_duration_frame, textvariable=self.fade_out_duration_var, width=3).grid(row=0, column=1)

    def _create_banner_tab(self):
        tab = ttk.Frame(self.notebook, padding=(20, 15))
        self.notebook.add(tab, text=" Editor: Faixa ")
        tab.columnconfigure(0, weight=1)
        self._create_banner_section(tab, row=0)

    def _create_audio_tab(self):
        # ... (sem alterações) ...
        tab = ttk.Frame(self.notebook, padding=(20, 15))
        self.notebook.add(tab, text=" Editor: Áudio ")
        tab.columnconfigure(0, weight=1)
        audio_settings_section = ttk.LabelFrame(tab, text=" Volumes ", padding=15)
        audio_settings_section.grid(row=0, column=0, sticky="ew")
        audio_settings_section.columnconfigure(1, weight=1)

        self._create_volume_slider(audio_settings_section, 0, "Volume da Narração:", self.narration_volume_var, -20, 20)
        self._create_volume_slider(audio_settings_section, 1, "Volume da Música:", self.music_volume_var, -60, 0)

    def _create_intro_tab(self):
        tab = ttk.Frame(self.notebook, padding=(20, 15))
        self.notebook.add(tab, text=" Editor: Introdução ")
        tab.columnconfigure(0, weight=1)

        helper_box = ttk.LabelFrame(tab, text=" Como funciona? ", padding=15)
        helper_box.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        helper_text = (
            "• Ligue a introdução digitada para gerar um pequeno clipe com o texto antes do conteúdo.\n"
            "• Escreva o texto uma única vez e nós traduziremos automaticamente para o idioma do vídeo.\n"
            "• Personalize a fonte e o negrito para combinar com a identidade visual desejada.\n"
            "• Ajuste o idioma preferido apenas se precisar forçar um idioma específico."
        )
        ttk.Label(helper_box, text=helper_text, justify=LEFT, wraplength=780).grid(row=0, column=0, sticky="w")

        settings_box = ttk.LabelFrame(tab, text=" Passo a passo ", padding=15)
        settings_box.grid(row=1, column=0, sticky="ew", pady=(0, 15))
        settings_box.columnconfigure(1, weight=1)

        self.intro_enabled_check = ttk.Checkbutton(
            settings_box,
            text="1) Ativar introdução digitada com áudio sincronizado",
            variable=self.intro_enabled_var,
            bootstyle="round-toggle",
            command=self._refresh_intro_state
        )
        self.intro_enabled_check.grid(row=0, column=0, columnspan=2, sticky="w")
        ToolTip(self.intro_enabled_check, "Quando ligado, cada renderização começará com o texto digitado antes do conteúdo principal.")

        single_language_frame = ttk.Frame(settings_box)
        single_language_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 5))
        single_language_frame.columnconfigure(1, weight=1)
        ttk.Label(single_language_frame, text="2) Idioma preferido para vídeos únicos/slideshow:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.single_language_combobox = ttk.Combobox(
            single_language_frame,
            textvariable=self.single_language_display_var,
            state="readonly",
            values=list(self.language_code_to_display.values())
        )
        self.single_language_combobox.grid(row=0, column=1, sticky="ew")
        self.single_language_combobox.bind("<<ComboboxSelected>>", self._on_single_language_selected)
        ttk.Label(single_language_frame, text="Escolha o idioma manualmente ou deixe em Automático para detectar pelo arquivo.", bootstyle="secondary", wraplength=760).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        ttk.Label(settings_box, text="3) Idioma padrão para vídeos em lote:").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=(12, 5))
        self._intro_language_choices = [("auto", "Automático (usar idioma do vídeo)")]
        for code, label in LANGUAGE_CODE_MAP.items():
            self._intro_language_choices.append((code, f"{label} ({code})"))

        self.intro_language_display_var = ttk.StringVar()
        self.intro_language_combobox = ttk.Combobox(
            settings_box,
            textvariable=self.intro_language_display_var,
            state="readonly",
            values=[label for _, label in self._intro_language_choices]
        )
        self.intro_language_combobox.grid(row=2, column=1, sticky="ew", pady=(12, 5))
        self.intro_language_combobox.bind("<<ComboboxSelected>>", lambda event: self._on_intro_language_selected())
        ttk.Label(settings_box, text="Quando automático, cada vídeo usa o texto configurado para o idioma detectado.", bootstyle="secondary", wraplength=760).grid(row=3, column=0, columnspan=2, sticky="w")

        ttk.Label(settings_box, text="4) Personalize a tipografia da introdução:").grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 5))

        intro_font_frame = ttk.Frame(settings_box)
        intro_font_frame.grid(row=5, column=0, columnspan=2, sticky="ew")
        intro_font_frame.columnconfigure(1, weight=1)

        ttk.Label(intro_font_frame, text="Fonte:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.intro_font_choice_combobox = ttk.Combobox(
            intro_font_frame,
            textvariable=self.intro_font_choice_var,
            state="readonly",
            values=INTRO_FONT_CHOICES,
        )
        self.intro_font_choice_combobox.grid(row=0, column=1, sticky="ew")

        self.intro_font_bold_check = ttk.Checkbutton(
            intro_font_frame,
            text="Negrito",
            variable=self.intro_font_bold_var,
            bootstyle="round-toggle",
        )
        self.intro_font_bold_check.grid(row=0, column=2, sticky="w", padx=(12, 0))
        ToolTip(self.intro_font_bold_check, "Ativa letras mais encorpadas para destacar a introdução.")

        ttk.Label(settings_box, text="5) Ajuste a velocidade da digitação e a pausa final:").grid(row=6, column=0, columnspan=2, sticky="w", pady=(12, 5))

        intro_timing_frame = ttk.Frame(settings_box)
        intro_timing_frame.grid(row=7, column=0, columnspan=2, sticky="ew")
        intro_timing_frame.columnconfigure(1, weight=1)
        intro_timing_frame.columnconfigure(3, weight=1)

        ttk.Label(intro_timing_frame, text="Duração da animação (s):").grid(row=0, column=0, sticky="w", padx=(0, 10))
        typing_duration_choices = ["10", "15", "20", "30"]
        self.intro_typing_duration_combobox = ttk.Combobox(
            intro_timing_frame,
            textvariable=self.intro_typing_duration_seconds_var,
            values=typing_duration_choices,
            state="readonly",
            width=8,
        )
        self.intro_typing_duration_combobox.grid(row=0, column=1, sticky="w")
        self.intro_typing_duration_combobox.set(str(self.intro_typing_duration_seconds_var.get()))
        ToolTip(
            self.intro_typing_duration_combobox,
            "Controla quanto tempo a animação de digitação deve demorar antes de concluir.",
        )

        ttk.Label(intro_timing_frame, text="Pausa final (s):").grid(row=0, column=2, sticky="w", padx=(20, 10))
        self.intro_hold_duration_spinbox = ttk.Spinbox(
            intro_timing_frame,
            from_=1,
            to=15,
            increment=1,
            textvariable=self.intro_hold_duration_seconds_var,
            width=5,
            state="readonly",
        )
        self.intro_hold_duration_spinbox.grid(row=0, column=3, sticky="w")
        ToolTip(
            self.intro_hold_duration_spinbox,
            "Define por quantos segundos a tela final permanece visível antes do conteúdo principal.",
        )

        ttk.Label(settings_box, text="6) Texto da introdução (será traduzido automaticamente quando necessário):").grid(row=8, column=0, columnspan=2, sticky="w", pady=(12, 5))
        self.intro_default_text_widget = scrolledtext.ScrolledText(settings_box, height=6, wrap="word")
        self.intro_default_text_widget.grid(row=9, column=0, columnspan=2, sticky="ew")
        settings_box.rowconfigure(9, weight=1)
        self.intro_default_text_widget.insert("1.0", self.intro_default_text_var.get())
        tab.rowconfigure(1, weight=1)
        self._set_intro_language_display_from_code(self.intro_language_var.get())
        self._refresh_intro_state()

    def _set_intro_language_display_from_code(self, code: str):
        selected_label = next((label for value, label in self._intro_language_choices if value == code), None)
        if not selected_label:
            selected_label = self._intro_language_choices[0][1]
            self.intro_language_var.set(self._intro_language_choices[0][0])
        self.intro_language_display_var.set(selected_label)

    def _on_intro_language_selected(self):
        current_label = self.intro_language_display_var.get()
        for value, label in self._intro_language_choices:
            if label == current_label:
                self.intro_language_var.set(value)
                break

    def _refresh_intro_state(self):
        enabled = self.intro_enabled_var.get()
        state = NORMAL if enabled else DISABLED
        if hasattr(self, 'single_language_combobox'):
            self.single_language_combobox.configure(state="readonly" if enabled else DISABLED)
        if hasattr(self, 'intro_language_combobox'):
            self.intro_language_combobox.configure(state="readonly" if enabled else DISABLED)
        if hasattr(self, 'intro_font_choice_combobox'):
            self.intro_font_choice_combobox.configure(state="readonly" if enabled else DISABLED)
        if hasattr(self, 'intro_font_bold_check'):
            self.intro_font_bold_check.configure(state=NORMAL if enabled else DISABLED)
        if hasattr(self, 'intro_typing_duration_combobox'):
            self.intro_typing_duration_combobox.configure(state="readonly" if enabled else DISABLED)
        if hasattr(self, 'intro_hold_duration_spinbox'):
            self.intro_hold_duration_spinbox.configure(state="readonly" if enabled else DISABLED)
        if hasattr(self, 'intro_default_text_widget'):
            self.intro_default_text_widget.configure(state=state)

    def _collect_intro_texts(self) -> Dict[str, str]:
        return {}

    def _create_banner_section(self, tab, row: int = 1):
        tab.rowconfigure(row, weight=1)
        banner_section = ttk.LabelFrame(tab, text=" Faixa de Destaque ", padding=15)
        banner_section.grid(row=row, column=0, sticky="nsew")
        banner_section.columnconfigure(0, weight=1)

        header_row = 0
        self.banner_enabled_check = ttk.Checkbutton(
            banner_section,
            text="Ativar faixa informativa no início do vídeo",
            variable=self.banner_enabled_var,
            bootstyle="round-toggle",
            command=lambda: (self._refresh_banner_state(), self.on_banner_settings_change()),
        )
        self.banner_enabled_check.grid(row=header_row, column=0, sticky="w")
        header_row += 1

        ttk.Label(
            banner_section,
            text=(
                "A faixa é exibida logo após a digitalização, quando o vídeo principal começa, "
                "e permanece durante todo o conteúdo."
            ),
            wraplength=420,
            justify=LEFT,
        ).grid(row=header_row, column=0, sticky="w", pady=(6, 2))
        header_row += 1

        content_pane = ttk.PanedWindow(banner_section, orient=HORIZONTAL)
        content_pane.grid(row=header_row, column=0, sticky="nsew", pady=(12, 0))
        banner_section.rowconfigure(header_row, weight=1)

        controls_frame = ttk.Frame(content_pane, padding=(0, 0, 12, 0))
        controls_frame.columnconfigure(0, weight=1)

        preview_container = ttk.Frame(content_pane, padding=(12, 0, 0, 0))
        preview_container.rowconfigure(0, weight=1)
        preview_container.columnconfigure(0, weight=1)

        content_pane.add(controls_frame, weight=3)
        content_pane.add(preview_container, weight=2)

        control_row = 0

        language_frame = ttk.Frame(controls_frame)
        language_frame.grid(row=control_row, column=0, sticky="ew")
        language_frame.columnconfigure(1, weight=1)
        ttk.Label(language_frame, text="Idioma preferido para traduções automáticas:").grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        self.banner_language_display_var = ttk.StringVar()
        self.banner_language_combobox = ttk.Combobox(
            language_frame,
            textvariable=self.banner_language_display_var,
            values=list(self.language_code_to_display.values()),
            state="readonly",
        )
        self.banner_language_combobox.grid(row=0, column=1, sticky="ew")
        self.banner_language_combobox.bind(
            "<<ComboboxSelected>>", lambda event: self._on_banner_language_selected()
        )
        self._set_banner_language_display_from_code(self.banner_language_code_var.get())
        control_row += 1

        self.banner_duration_frame = self._create_slider_control(
            controls_frame,
            control_row,
            "Duração (s):",
            self.banner_duration_var,
            1.0,
            15.0,
            "%.1f",
            self.on_banner_settings_change,
        )
        control_row += 1

        self.banner_height_ratio_frame = self._create_slider_control(
            controls_frame,
            control_row,
            "Altura da faixa:",
            self.banner_height_ratio_var,
            0.05,
            0.40,
            "%.0f%%",
            self.on_banner_settings_change,
            display_transform=lambda v: v * 100,
        )
        control_row += 1

        self.banner_font_scale_frame = self._create_slider_control(
            controls_frame,
            control_row,
            "Escala do texto:",
            self.banner_font_scale_var,
            0.20,
            1.20,
            "%.2fx",
            self.on_banner_settings_change,
        )
        control_row += 1

        colors_frame = ttk.LabelFrame(controls_frame, text=" Cores da Faixa ", padding=10)
        colors_frame.grid(row=control_row, column=0, sticky="ew", pady=(10, 0))
        colors_frame.columnconfigure(1, weight=1)

        color_mode_frame = ttk.Frame(colors_frame)
        color_mode_frame.grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(color_mode_frame, text="Modo de preenchimento:").grid(row=0, column=0, sticky="w", padx=(0, 10))

        self._banner_color_mode_buttons = []
        for idx, (value, label) in enumerate(((False, "Cor única"), (True, "Degradê"))):
            btn = ttk.Radiobutton(
                color_mode_frame,
                text=label,
                variable=self.banner_use_gradient_var,
                value=value,
                bootstyle="outline-toolbutton",
                command=lambda v=value: self._on_banner_color_mode_selected(v),
            )
            btn.grid(row=0, column=idx + 1, sticky="w", padx=(0 if idx == 0 else 6, 0))
            self._banner_color_mode_buttons.append((value, btn))

        ttk.Label(colors_frame, text="Cor única:").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(5, 0))
        solid_picker = self._create_color_picker(
            colors_frame, 1, 1, self.banner_solid_color_var, self.on_banner_settings_change
        )
        ttk.Label(colors_frame, text="Início do degradê:").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=(5, 0))
        gradient_start_picker = self._create_color_picker(
            colors_frame, 2, 1, self.banner_gradient_start_var, self.on_banner_settings_change
        )
        ttk.Label(colors_frame, text="Fim do degradê:").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=(5, 0))
        gradient_end_picker = self._create_color_picker(
            colors_frame, 3, 1, self.banner_gradient_end_var, self.on_banner_settings_change
        )
        self._banner_color_frames = [solid_picker, gradient_start_picker, gradient_end_picker]
        control_row += 1

        font_frame = ttk.Frame(controls_frame)
        font_frame.grid(row=control_row, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(font_frame, text="Cor do texto:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.banner_font_color_picker = self._create_color_picker(
            font_frame, 0, 1, self.banner_font_color_var, self.on_banner_settings_change
        )
        control_row += 1

        text_effects_frame = ttk.LabelFrame(controls_frame, text=" Estilo do Texto ", padding=10)
        text_effects_frame.grid(row=control_row, column=0, sticky="ew", pady=(10, 0))
        text_effects_frame.columnconfigure(1, weight=1)

        effect_row = 0
        self.banner_outline_check = ttk.Checkbutton(
            text_effects_frame,
            text="Adicionar contorno",
            variable=self.banner_outline_enabled_var,
            bootstyle="round-toggle",
            command=self._on_banner_outline_toggle,
        )
        self.banner_outline_check.grid(row=effect_row, column=0, columnspan=2, sticky="w")
        effect_row += 1

        ttk.Label(text_effects_frame, text="Cor do contorno:").grid(
            row=effect_row, column=0, sticky="w", padx=(0, 10), pady=(5, 0)
        )
        self.banner_outline_color_picker = self._create_color_picker(
            text_effects_frame,
            effect_row,
            1,
            self.banner_outline_color_var,
            self.on_banner_settings_change,
        )
        effect_row += 1

        outline_offset_frame = self._create_slider_control(
            text_effects_frame,
            effect_row,
            "Espessura/offset (px):",
            self.banner_outline_offset_var,
            0.0,
            20.0,
            "%.0f",
            self.on_banner_settings_change,
        )
        effect_row += 1

        self.banner_shadow_check = ttk.Checkbutton(
            text_effects_frame,
            text="Adicionar sombra",
            variable=self.banner_shadow_enabled_var,
            bootstyle="round-toggle",
            command=self._on_banner_shadow_toggle,
        )
        self.banner_shadow_check.grid(row=effect_row, column=0, columnspan=2, sticky="w", pady=(10, 0))
        effect_row += 1

        ttk.Label(text_effects_frame, text="Cor da sombra:").grid(
            row=effect_row, column=0, sticky="w", padx=(0, 10), pady=(5, 0)
        )
        self.banner_shadow_color_picker = self._create_color_picker(
            text_effects_frame,
            effect_row,
            1,
            self.banner_shadow_color_var,
            self.on_banner_settings_change,
        )
        effect_row += 1

        shadow_offset_x_frame = self._create_slider_control(
            text_effects_frame,
            effect_row,
            "Offset X (px):",
            self.banner_shadow_offset_x_var,
            -30.0,
            30.0,
            "%.0f",
            self.on_banner_settings_change,
        )
        effect_row += 1

        shadow_offset_y_frame = self._create_slider_control(
            text_effects_frame,
            effect_row,
            "Offset Y (px):",
            self.banner_shadow_offset_y_var,
            -30.0,
            30.0,
            "%.0f",
            self.on_banner_settings_change,
        )

        self._banner_outline_widgets = [
            self.banner_outline_color_picker,
            outline_offset_frame,
        ]
        self._banner_shadow_widgets = [
            self.banner_shadow_color_picker,
            shadow_offset_x_frame,
            shadow_offset_y_frame,
        ]
        control_row += 1

        ttk.Label(controls_frame, text="Texto da faixa:").grid(
            row=control_row, column=0, sticky="w", pady=(10, 5)
        )
        control_row += 1

        controls_frame.rowconfigure(control_row, weight=1)
        self.banner_default_text_widget = scrolledtext.ScrolledText(controls_frame, height=6, wrap="word")
        self.banner_default_text_widget.grid(row=control_row, column=0, sticky="nsew")
        self.banner_default_text_widget.insert("1.0", self.banner_default_text_var.get())
        self.banner_default_text_widget.bind("<KeyRelease>", self._on_banner_default_text_change)

        preview_frame = ttk.LabelFrame(
            preview_container, text=" Pré-visualização da Faixa ", padding=12
        )
        preview_frame.grid(row=0, column=0, sticky="nsew")
        preview_frame.rowconfigure(0, weight=1, minsize=320)
        preview_frame.columnconfigure(0, weight=1)
        self.banner_preview = BannerPreview(preview_frame, height=400)
        self.banner_preview.grid(row=0, column=0, sticky="nsew")

        self._refresh_banner_state()
        self._refresh_banner_gradient_state()
        self._refresh_banner_effect_states()

    def _set_banner_language_display_from_code(self, code: str):
        display = self.language_code_to_display.get(code, self.language_code_to_display.get("auto"))
        if not display:
            display = next(iter(self.language_code_to_display.values()))
            code = self.language_display_to_code.get(display, "auto")
        self.banner_language_display_var.set(display)
        resolved_code = self.language_display_to_code.get(display, "auto")
        self.banner_language_code_var.set(resolved_code)

    def _on_banner_language_selected(self):
        current_label = self.banner_language_display_var.get()
        code = self.language_display_to_code.get(current_label, "auto")
        self.banner_language_code_var.set(code)
        self.on_banner_settings_change()

    def _on_banner_default_text_change(self, event=None):
        text = self.banner_default_text_widget.get("1.0", "end").strip()
        self.banner_default_text_var.set(text)
        self.on_banner_settings_change()

    def _on_banner_color_mode_selected(self, use_gradient: bool):
        self.banner_use_gradient_var.set(use_gradient)
        self._refresh_banner_gradient_state()
        self._refresh_banner_color_mode_buttons()
        self.on_banner_settings_change()

    def _refresh_banner_state(self):
        enabled = self.banner_enabled_var.get()
        combo_state = "readonly" if enabled else DISABLED
        general_state = NORMAL if enabled else DISABLED
        if hasattr(self, 'banner_language_combobox'):
            self.banner_language_combobox.configure(state=combo_state)
        for frame_attr in (
            'banner_duration_frame',
            'banner_height_ratio_frame',
            'banner_font_scale_frame',
        ):
            frame = getattr(self, frame_attr, None)
            if frame is None:
                continue
            for child in frame.winfo_children():
                try:
                    child.configure(state=general_state)
                except Exception:
                    for grandchild in child.winfo_children():
                        try:
                            grandchild.configure(state=general_state)
                        except Exception:
                            pass
        if hasattr(self, 'banner_default_text_widget'):
            self.banner_default_text_widget.configure(state=general_state)
        if hasattr(self, '_banner_color_mode_buttons'):
            for _, button in self._banner_color_mode_buttons:
                try:
                    button.configure(state=general_state)
                except Exception:
                    pass
            self._refresh_banner_color_mode_buttons()
        if hasattr(self, '_banner_color_frames'):
            for frame in self._banner_color_frames:
                for child in frame.winfo_children():
                    try:
                        child.configure(state=general_state)
                    except Exception:
                        pass
        if hasattr(self, 'banner_font_color_picker'):
            for child in self.banner_font_color_picker.winfo_children():
                try:
                    child.configure(state=general_state)
                except Exception:
                    pass
        self._refresh_banner_gradient_state()
        self._refresh_banner_effect_states()

    def _refresh_banner_color_mode_buttons(self):
        if not hasattr(self, '_banner_color_mode_buttons'):
            return
        use_gradient = bool(self.banner_use_gradient_var.get())
        for value, button in self._banner_color_mode_buttons:
            try:
                style = "primary-toolbutton" if bool(value) == use_gradient else "outline-toolbutton"
                button.configure(bootstyle=style)
            except Exception:
                pass

    def _refresh_banner_gradient_state(self):
        enabled = self.banner_enabled_var.get()
        use_gradient = self.banner_use_gradient_var.get()
        if not hasattr(self, '_banner_color_frames'):
            return
        frames = self._banner_color_frames
        for idx, frame in enumerate(frames):
            if idx == 0:
                allow = enabled and not use_gradient
            else:
                allow = enabled and use_gradient
            state = NORMAL if allow else DISABLED
            for child in frame.winfo_children():
                try:
                    child.configure(state=state)
                except Exception:
                    pass

    def _configure_widget_state_recursive(self, widget, state):
        try:
            widget.configure(state=state)
        except Exception:
            pass
        if hasattr(widget, 'winfo_children'):
            for child in widget.winfo_children():
                self._configure_widget_state_recursive(child, state)

    def _set_widgets_enabled(self, widgets, enabled: bool):
        state = NORMAL if enabled else DISABLED
        for widget in widgets:
            self._configure_widget_state_recursive(widget, state)

    def _refresh_banner_effect_states(self):
        enabled = self.banner_enabled_var.get()
        general_state = NORMAL if enabled else DISABLED
        if hasattr(self, 'banner_outline_check'):
            try:
                self.banner_outline_check.configure(state=general_state)
            except Exception:
                pass
        if hasattr(self, 'banner_shadow_check'):
            try:
                self.banner_shadow_check.configure(state=general_state)
            except Exception:
                pass
        outline_var = getattr(self, 'banner_outline_enabled_var', None)
        shadow_var = getattr(self, 'banner_shadow_enabled_var', None)
        outline_active = enabled and bool(outline_var.get() if outline_var is not None else False)
        shadow_active = enabled and bool(shadow_var.get() if shadow_var is not None else False)
        if hasattr(self, '_banner_outline_widgets'):
            self._set_widgets_enabled(self._banner_outline_widgets, outline_active)
        if hasattr(self, '_banner_shadow_widgets'):
            self._set_widgets_enabled(self._banner_shadow_widgets, shadow_active)

    def _on_banner_outline_toggle(self):
        self._refresh_banner_effect_states()
        self.on_banner_settings_change()

    def _on_banner_shadow_toggle(self):
        self._refresh_banner_effect_states()
        self.on_banner_settings_change()

    def on_banner_settings_change(self, event=None):
        if hasattr(self, '_banner_update_job') and self._banner_update_job is not None:
            try:
                self.root.after_cancel(self._banner_update_job)
            except Exception:
                pass
            finally:
                self._banner_update_job = None

        # Atualiza imediatamente para que os controles respondam em tempo real.
        self.update_banner_preview_job()

        # Proteção leve para garantir que a última alteração seja refletida
        # mesmo que múltiplos eventos ocorram em sequência muito rápida.
        self._banner_update_job = self.root.after(80, self.update_banner_preview_job)

    def update_banner_preview_job(self):
        if not hasattr(self, 'banner_preview'):
            return
        enabled = self.banner_enabled_var.get()
        default_text = self.banner_default_text_var.get().strip()
        text_to_show = default_text
        res = self.resolution_var.get() if hasattr(self, 'resolution_var') else "1920x1080"
        video_w, video_h = self._parse_resolution_string(res)
        font_path = self.subtitle_font_file.get() if hasattr(self, 'subtitle_font_file') else ""
        try:
            self.banner_preview.update_preview(
                text=text_to_show,
                use_gradient=self.banner_use_gradient_var.get(),
                solid_color=self.banner_solid_color_var.get(),
                gradient_start=self.banner_gradient_start_var.get(),
                gradient_end=self.banner_gradient_end_var.get(),
                font_color=self.banner_font_color_var.get(),
                enabled=enabled,
                video_resolution=(video_w, video_h),
                height_ratio=self.banner_height_ratio_var.get(),
                font_scale=self.banner_font_scale_var.get(),
                font_path=font_path or None,
                outline_enabled=self.banner_outline_enabled_var.get(),
                outline_color=self.banner_outline_color_var.get(),
                outline_offset=self.banner_outline_offset_var.get(),
                shadow_enabled=self.banner_shadow_enabled_var.get(),
                shadow_color=self.banner_shadow_color_var.get(),
                shadow_offset_x=self.banner_shadow_offset_x_var.get(),
                shadow_offset_y=self.banner_shadow_offset_y_var.get(),
            )
        except Exception as exc:
            logger.error("Erro ao atualizar pré-visualização da faixa: %s", exc, exc_info=True)

    @staticmethod
    def _parse_resolution_string(resolution: Optional[str]):
        if not resolution:
            return 1920, 1080
        match = re.search(r"(\d{3,5})\s*[xX]\s*(\d{3,5})", resolution)
        if match:
            width, height = int(match.group(1)), int(match.group(2))
            if width > 0 and height > 0:
                return width, height
        match = re.search(r"(\d{3,4})p", resolution, re.IGNORECASE)
        if match:
            height = int(match.group(1))
            if height > 0:
                width = int(round(height * 16 / 9))
                return width, height
        return 1920, 1080

    def _create_effects_tab(self):
        # ... (sem alterações) ...
        tab = ttk.Frame(self.notebook, padding=(20, 15))
        self.notebook.add(tab, text=" Editor: Efeitos ")
        tab.columnconfigure(0, weight=1)

        effects_section = ttk.LabelFrame(tab, text=" Efeitos de Overlay de Vídeo ", padding=15)
        effects_section.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        effects_section.columnconfigure(0, weight=1)
        
        self._create_file_input(effects_section, 0, "Arquivo de Efeito (.mp4):", 'effect_overlay', lambda: self.select_file('effect_overlay', "Selecione o vídeo de efeito", SUPPORTED_VIDEO_FT), hint_text=None)
        
        blend_frame = ttk.Frame(effects_section)
        blend_frame.grid(row=1, column=0, sticky="ew", pady=4)
        blend_frame.columnconfigure(1, weight=1)
        ttk.Label(blend_frame, text="Modo de Mesclagem:", width=25, anchor='w').grid(row=0, column=0, sticky="w", padx=(0, 10))
        blend_combo = ttk.Combobox(blend_frame, textvariable=self.effect_blend_mode_var, values=list(EFFECT_BLEND_MODES.keys()), state="readonly")
        blend_combo.grid(row=0, column=1, sticky="ew")
        ToolTip(blend_combo, "Como o vídeo de efeito será misturado com o vídeo principal.")

    def _create_volume_slider(self, parent, row, label_text, var, from_, to):
        # ... (sem alterações) ...
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky="w", padx=(0,10), pady=10)
        slider_frame = ttk.Frame(parent)
        slider_frame.grid(row=row, column=1, sticky="ew")
        slider_frame.columnconfigure(0, weight=1)
        
        display_var = ttk.StringVar()
        def update_display(v):
            val = int(float(v))
            var.set(val)
            display_var.set(f"{val} dB")
        
        ttk.Scale(slider_frame, from_=from_, to=to, variable=var, orient=HORIZONTAL, command=update_display).grid(row=0, column=0, sticky="ew", padx=(0,10))
        ttk.Label(slider_frame, textvariable=display_var, width=7).grid(row=0, column=1)
        update_display(var.get())

    def _create_subtitle_tab(self):
        tab = ttk.Frame(self.notebook, padding=(20, 15))
        self.notebook.add(tab, text=" Editor: Legendas ")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        header_frame = ttk.Frame(tab, padding=(0, 0, 0, 15))
        header_frame.grid(row=0, column=0, sticky="ew")
        header_frame.columnconfigure(0, weight=1)

        ttk.Label(
            header_frame,
            text="Personalize suas legendas",
            font=("Segoe UI", 14, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header_frame,
            text="Ajuste tamanho, posição e cores para combinar com o seu vídeo.",
            bootstyle="secondary",
        ).grid(row=1, column=0, sticky="w", pady=(5, 0))

        main_pane = ttk.PanedWindow(tab, orient=HORIZONTAL)
        main_pane.grid(row=1, column=0, sticky="nsew")

        controls_container = ttk.Frame(main_pane, padding=15)
        controls_container.columnconfigure(0, weight=1)
        main_pane.add(controls_container, weight=3)

        style_section = ttk.LabelFrame(controls_container, text=" Aparência e Layout ", padding=15)
        style_section.grid(row=0, column=0, sticky="ew")
        style_section.columnconfigure(1, weight=1)
        style_section.columnconfigure(3, weight=1)

        self._create_font_size_slider(style_section, 0, 0)
        ttk.Label(style_section, text="Posição:").grid(row=0, column=2, sticky="w", padx=(20,10), pady=5)
        pos_combo = ttk.Combobox(
            style_section,
            textvariable=self.subtitle_position_var,
            values=list(SUBTITLE_POSITIONS.keys()),
            state="readonly",
        )
        pos_combo.grid(row=0, column=3, sticky="ew")
        pos_combo.bind('<<ComboboxSelected>>', self.on_subtitle_style_change)

        ttk.Label(style_section, text="Cor do Texto:").grid(row=1, column=0, sticky="w", padx=(0,10), pady=5)
        self._create_color_picker(style_section, 1, 1, self.subtitle_textcolor_var, self.on_subtitle_style_change)
        ttk.Label(style_section, text="Cor do Contorno:").grid(row=1, column=2, sticky="w", padx=(20,10), pady=5)
        self._create_color_picker(style_section, 1, 3, self.subtitle_outlinecolor_var, self.on_subtitle_style_change)

        style_frame = ttk.Frame(style_section)
        style_frame.grid(row=2, column=1, sticky="w", pady=5)
        ttk.Checkbutton(
            style_frame,
            text="Negrito",
            variable=self.subtitle_bold_var,
            bootstyle="round-toggle",
            command=self.on_subtitle_style_change,
        ).pack(side=LEFT, padx=(0, 10))
        ttk.Checkbutton(
            style_frame,
            text="Itálico",
            variable=self.subtitle_italic_var,
            bootstyle="round-toggle",
            command=self.on_subtitle_style_change,
        ).pack(side=LEFT)

        font_section = ttk.LabelFrame(controls_container, text=" Fonte Personalizada ", padding=15)
        font_section.grid(row=1, column=0, sticky="ew", pady=(15, 0))
        font_section.columnconfigure(1, weight=1)

        ttk.Label(font_section, text="Ficheiro de Fonte:", width=18, anchor='w').grid(row=0, column=0, sticky="w", padx=(0, 10))

        entry = ttk.Entry(font_section, textvariable=self.subtitle_font_file, state="readonly")
        entry.grid(row=0, column=1, sticky="ew", padx=(0, 5))

        select_button = ttk.Button(
            font_section,
            text="Selecionar...",
            command=lambda: self.select_file('subtitle_font', "Selecione a Fonte", SUPPORTED_FONT_FT, callback=self.on_subtitle_style_change),
            bootstyle="secondary-outline",
            width=12,
        )
        select_button.grid(row=0, column=2, sticky="e")

        clear_button = ttk.Button(
            font_section,
            text="Limpar",
            command=self.reset_subtitle_font,
            bootstyle="danger-outline",
            width=8,
        )
        clear_button.grid(row=0, column=3, sticky="e", padx=(5,0))
        ToolTip(clear_button, "Voltar para a fonte padrão")

        preview_container = ttk.Frame(main_pane, padding=15)
        preview_container.columnconfigure(0, weight=1)
        preview_container.rowconfigure(1, weight=1)
        main_pane.add(preview_container, weight=4)

        ttk.Label(
            preview_container,
            text="Pré-visualização da legenda",
            font=("Segoe UI", 12, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        preview_section = ttk.LabelFrame(preview_container, padding=10)
        preview_section.grid(row=1, column=0, sticky="nsew")
        preview_section.rowconfigure(0, weight=1)
        preview_section.columnconfigure(0, weight=1)

        self.subtitle_preview = SubtitlePreview(preview_section, self)
        self.subtitle_preview.grid(row=0, column=0, sticky="nsew")

    def _create_overlay_tab(self):
        # ... (sem alterações) ...
        tab = ttk.Frame(self.notebook, padding=(20, 15))
        self.notebook.add(tab, text=" Editor: Sobreposições ")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)

        main_pane = ttk.PanedWindow(tab, orient=HORIZONTAL)
        main_pane.grid(row=0, column=0, sticky="nsew")

        controls_frame = ttk.Frame(main_pane, padding=10)
        main_pane.add(controls_frame, weight=1)
        controls_frame.columnconfigure(0, weight=1)

        png_section = ttk.LabelFrame(controls_frame, text=" Marca d'água (PNG) ", padding=15)
        png_section.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        png_section.columnconfigure(0, weight=1)
        
        self._create_file_input(png_section, 0, "Ficheiro PNG:", 'png_overlay', lambda: self.select_file('png_overlay', "Selecione o arquivo PNG", SUPPORTED_PNG_FT, callback=self.on_png_settings_change), hint_text=None)

        pos_frame = ttk.Frame(png_section)
        pos_frame.grid(row=1, column=0, sticky="ew", pady=4)
        pos_frame.columnconfigure(1, weight=1)
        ttk.Label(pos_frame, text="Posição:", width=15, anchor='w').grid(row=0, column=0, sticky="w", padx=(0, 10))
        png_pos_combo = ttk.Combobox(pos_frame, textvariable=self.png_overlay_position_var, values=OVERLAY_POSITIONS, state="readonly")
        png_pos_combo.grid(row=0, column=1, sticky="ew")
        png_pos_combo.bind("<<ComboboxSelected>>", self.on_png_settings_change)

        self._create_slider_control(png_section, 2, "Tamanho (Escala):", self.png_overlay_scale_var, 0.01, 1.0, "%.2f", self.on_png_settings_change)
        self._create_slider_control(png_section, 3, "Opacidade:", self.png_overlay_opacity_var, 0.0, 1.0, "%.2f", self.on_png_settings_change)

        presenter_section = ttk.LabelFrame(controls_frame, text=" Apresentador Animado ", padding=15)
        presenter_section.grid(row=1, column=0, sticky="ew")
        presenter_section.columnconfigure(1, weight=1)

        self._create_file_input(presenter_section, 0, "Vídeo do Apresentador:", 'presenter_video', lambda: self.select_file('presenter_video', "Selecione o vídeo do apresentador", SUPPORTED_PRESENTER_FT, callback=self.on_presenter_settings_change), hint_text=None)
        
        presenter_pos_frame = ttk.Frame(presenter_section)
        presenter_pos_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=4)
        presenter_pos_frame.columnconfigure(1, weight=1)

        ttk.Label(presenter_pos_frame, text="Posição:").grid(row=0, column=0, sticky="w", padx=(0,10), pady=5)
        presenter_pos_combo = ttk.Combobox(presenter_pos_frame, textvariable=self.presenter_position_var, values=PRESENTER_POSITIONS, state="readonly")
        presenter_pos_combo.grid(row=0, column=1, sticky="ew")
        presenter_pos_combo.bind("<<ComboboxSelected>>", self.on_presenter_settings_change)

        self._create_slider_control(
            presenter_section, 2,
            "Tamanho (Escala):", self.presenter_scale_var,
            0.05, 0.80, "%.2f",
            self.on_presenter_settings_change
        )
        
        chroma_frame = ttk.LabelFrame(presenter_section, text=" Chroma Key (Fundo Verde) ", padding=10)
        chroma_frame.grid(row=3, column=0, columnspan=2, sticky='ew', pady=(10,0))
        chroma_frame.columnconfigure(1, weight=1)

        cb_chroma = ttk.Checkbutton(chroma_frame, text="Ativar Remoção de Fundo", variable=self.presenter_chroma_enabled_var, bootstyle="round-toggle", command=self.on_presenter_settings_change)
        cb_chroma.grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 10))
        ToolTip(cb_chroma, "Ative se o vídeo do apresentador tiver um fundo de cor sólida (verde, azul, etc.) para ser removido.")

        ttk.Label(chroma_frame, text="Cor do Fundo:").grid(row=1, column=0, sticky="w", padx=(0,10), pady=5)
        self._create_color_picker(chroma_frame, 1, 1, self.presenter_chroma_color_var, self.on_presenter_settings_change)

        self._create_slider_control(
            chroma_frame, 2, "Similaridade:", self.presenter_chroma_similarity_var,
            0.01, 1.0, "%.2f", self.on_presenter_settings_change
        )
        self._create_slider_control(
            chroma_frame, 3, "Suavização:", self.presenter_chroma_blend_var,
            0.0, 1.0, "%.2f", self.on_presenter_settings_change
        )

        preview_frame = ttk.Frame(main_pane, padding=10)
        main_pane.add(preview_frame, weight=2)
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.rowconfigure(1, weight=1)
        preview_frame.columnconfigure(0, weight=1)

        png_preview_section = ttk.LabelFrame(preview_frame, text=" Pré-visualização da Marca d'água ", padding=5)
        png_preview_section.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        png_preview_section.rowconfigure(0, weight=1)
        png_preview_section.columnconfigure(0, weight=1)
        self.png_preview = PngPreview(png_preview_section)
        self.png_preview.grid(row=0, column=0, sticky="nsew")

        presenter_preview_section = ttk.LabelFrame(preview_frame, text=" Pré-visualização do Apresentador ", padding=5)
        presenter_preview_section.grid(row=1, column=0, sticky="nsew")
        presenter_preview_section.rowconfigure(0, weight=1)
        presenter_preview_section.columnconfigure(0, weight=1)
        self.presenter_preview = PresenterPreview(presenter_preview_section)
        self.presenter_preview.grid(row=0, column=0, sticky="nsew")

    def _create_downloader_tab(self):
        # ... (sem alterações, mas o texto do url_frame já estava corrigido) ...
        tab = ttk.Frame(self.notebook, padding=(20, 15))
        self.notebook.add(tab, text=" Downloader ")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(4, weight=1)

        url_frame = ttk.LabelFrame(tab, text=" Cole as URLs (YouTube, Rutube, etc.) abaixo: ", padding=10)
        url_frame.grid(row=0, column=0, padx=0, pady=(0, 10), sticky="nsew")
        url_frame.columnconfigure(0, weight=1)
        url_frame.rowconfigure(0, weight=1)
        self.downloader_url_textbox = tk.Text(url_frame, height=8, wrap=WORD, relief="flat", background=self.root.style.colors.inputbg, foreground=self.root.style.colors.fg, insertbackground=self.root.style.colors.primary, bd=0)
        self.downloader_url_textbox.grid(row=0, column=0, sticky="nsew")

        options_frame = ttk.LabelFrame(tab, text=" Opções de Download ", padding=10)
        options_frame.grid(row=1, column=0, padx=0, pady=10, sticky="ew")
        options_frame.columnconfigure(1, weight=1)
        
        ttk.Button(options_frame, text="Selecionar Pasta de Destino", command=self._downloader_select_folder).grid(row=0, column=0, padx=(0,10), pady=10, sticky="w")
        self.downloader_folder_label = ttk.Label(options_frame, text=f"Salvar em: {self.download_output_path_var.get()}", anchor="w", wraplength=600)
        self.downloader_folder_label.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        ttk.Label(options_frame, text="Formato de Saída:").grid(row=1, column=0, padx=(0,10), pady=10, sticky="w")
        format_frame = ttk.Frame(options_frame)
        format_frame.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        ttk.Radiobutton(format_frame, text="Vídeo (MP4)", variable=self.download_format_var, value="MP4").pack(side=LEFT, padx=(0, 15))
        ttk.Radiobutton(format_frame, text="Áudio (MP3)", variable=self.download_format_var, value="MP3").pack(side=LEFT)

        playlist_frame = ttk.Frame(options_frame)
        playlist_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        playlist_frame.columnconfigure(2, weight=1)

        self.download_playlist_checkbutton = ttk.Checkbutton(
            playlist_frame,
            text="Baixar playlist completa",
            variable=self.download_playlist_enabled_var,
            command=self._downloader_on_playlist_toggle,
            bootstyle="round-toggle",
        )
        self.download_playlist_checkbutton.grid(row=0, column=0, padx=(0, 10), sticky="w")
        ToolTip(
            self.download_playlist_checkbutton,
            "Quando marcado, o yt-dlp baixa todos os itens da playlist encontrada na URL.",
        )

        ttk.Label(playlist_frame, text="Itens da playlist:").grid(row=0, column=1, padx=(0, 5), sticky="w")
        self.download_playlist_items_combobox = ttk.Combobox(
            playlist_frame,
            textvariable=self.download_playlist_items_var,
            values=("", "1-5", "1-10", "1-20", "1-50"),
            width=12,
        )
        self.download_playlist_items_combobox.grid(row=0, column=2, sticky="w")
        ToolTip(
            self.download_playlist_items_combobox,
            "Opcional: limite itens (ex.: 1-10 ou 1,3,5). Deixe em branco para todos os itens.",
        )
        self._downloader_on_playlist_toggle()

        action_frame = ttk.Frame(tab)
        action_frame.grid(row=2, column=0, padx=0, pady=10, sticky="ew")
        action_frame.columnconfigure(0, weight=1)
        
        self.downloader_button = ttk.Button(action_frame, text="Baixar Vídeos em Lote", command=self._downloader_start_thread, bootstyle=SUCCESS)
        self.downloader_button.grid(row=0, column=0, ipady=5, sticky="ew")
        
        progress_frame = ttk.LabelFrame(tab, text=" Progresso ", padding=10)
        progress_frame.grid(row=3, column=0, padx=0, pady=10, sticky="ew")
        progress_frame.columnconfigure(1, weight=1)

        self.downloader_status_label = ttk.Label(progress_frame, text="Aguardando...", anchor="w")
        self.downloader_status_label.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0,5))
        self.downloader_progress_bar = ttk.Progressbar(progress_frame, mode='determinate')
        self.downloader_progress_bar['value'] = 0
        self.downloader_progress_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0,10))

        ttk.Label(progress_frame, text="Progresso Geral:").grid(row=2, column=0, sticky="w")
        self.downloader_overall_progress_bar = ttk.Progressbar(progress_frame, mode='determinate', bootstyle=INFO)
        self.downloader_overall_progress_bar['value'] = 0
        self.downloader_overall_progress_bar.grid(row=3, column=0, sticky="ew", pady=(0,5))
        self.downloader_overall_status_label = ttk.Label(progress_frame, text="N/A", anchor="w")
        self.downloader_overall_status_label.grid(row=3, column=1, sticky="w", padx=(10,0))
        
        log_frame = ttk.LabelFrame(tab, text=" Logs do Downloader ", padding=10)
        log_frame.grid(row=4, column=0, sticky="nsew", padx=0, pady=(10,0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.downloader_log_textbox = scrolledtext.ScrolledText(log_frame, height=8, wrap=WORD, relief="flat", state=DISABLED, font=("Consolas", 9))
        self.downloader_log_textbox.grid(row=0, column=0, sticky="nsew")

    def _create_settings_tab(self):
        # ... (sem alterações) ...
        tab = ttk.Frame(self.notebook, padding=(20, 15))
        self.notebook.add(tab, text=" Configurações ")
        tab.columnconfigure(0, weight=1)
        
        ffmpeg_section = ttk.LabelFrame(tab, text=" FFmpeg e Diagnóstico ", padding=15)
        ffmpeg_section.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        ffmpeg_section.columnconfigure(0, weight=1)
        
        self._create_file_input(ffmpeg_section, 0, "Caminho do FFmpeg:", 'ffmpeg_path', self.ask_ffmpeg_path_manual, hint_text=None)
        
        tech_logs_cb = ttk.Checkbutton(ffmpeg_section, text="Mostrar detalhes técnicos (logs do FFmpeg)", variable=self.show_tech_logs_var, bootstyle="round-toggle")
        tech_logs_cb.grid(row=1, column=0, sticky='w', pady=(10,0))
        ToolTip(tech_logs_cb, "Se marcado, exibe mensagens de erro detalhadas do FFmpeg em caso de falha.")

        status_container = ttk.Frame(ffmpeg_section)
        status_container.grid(row=2, column=0, sticky='ew', pady=(10,0))
        
        install_button = ttk.Button(status_container, text="Instalar FFmpeg (Windows)", command=self.install_ffmpeg_automatically, bootstyle="info-outline")
        install_button.pack(side=LEFT, anchor='w')
        ToolTip(install_button, "Baixa e configura o FFmpeg automaticamente. Requer conexão com a internet.")
        
        logs_button = ttk.Button(status_container, text="Abrir Pasta de Logs", command=self.open_log_folder, bootstyle="secondary-outline")
        logs_button.pack(side=LEFT, padx=(10,0), anchor='w')
        ToolTip(logs_button, "Abre a pasta que contém o ficheiro de log 'app_main.log' para diagnóstico.")

        labels_frame = ttk.Frame(status_container)
        labels_frame.pack(side=LEFT, padx=15, anchor='w', fill='x', expand=True)

        self.ffmpeg_status_label = ttk.Label(labels_frame, text="Verificando FFmpeg...", bootstyle="secondary")
        self.ffmpeg_status_label.pack(anchor='w')
        
        self.gpu_status_label = ttk.Label(labels_frame, text="Verificando GPU...", bootstyle="secondary")
        self.gpu_status_label.pack(anchor='w', pady=(5,0))
        
        self.downloader_engine_status_label = ttk.Label(labels_frame, text="Verificando motor de download...", bootstyle="secondary")
        self.downloader_engine_status_label.pack(anchor='w', pady=(5,0))

    # ... (O restante da classe, como os métodos de lógica, permanecem os mesmos) ...
    def _create_slider_control(
        self,
        parent,
        row,
        label_text,
        var,
        from_,
        to,
        format_str,
        command,
        display_transform=None,
    ):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(10, 5))
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text=label_text, width=15, anchor='w').grid(row=0, column=0, sticky="w", padx=(0, 10))
        
        slider_frame = ttk.Frame(frame)
        slider_frame.grid(row=0, column=1, sticky="ew")
        slider_frame.columnconfigure(0, weight=1)
        
        display_var = ttk.StringVar()
        
        def update_display(v):
            val = float(v)
            var.set(val)
            display_value = display_transform(val) if display_transform else val
            display_var.set(format_str % display_value)
            if command:
                command()

        scale = ttk.Scale(slider_frame, from_=from_, to=to, variable=var, orient=HORIZONTAL, command=update_display)
        scale.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        
        label = ttk.Label(slider_frame, textvariable=display_var, width=5)
        label.grid(row=0, column=1)
        
        update_display(var.get())
        
        return frame

    def on_png_settings_change(self, event=None):
        if hasattr(self, '_png_update_job'): self.root.after_cancel(self._png_update_job)
        self._png_update_job = self.root.after(100, self.update_png_preview_job)

    def update_png_preview_job(self):
        if not hasattr(self, 'png_preview'): return
        self.png_preview.update_preview(
            logo_path=self.png_overlay_path_var.get(),
            position_key=self.png_overlay_position_var.get(),
            scale=self.png_overlay_scale_var.get(),
            opacity=self.png_overlay_opacity_var.get()
        )
    
    def on_presenter_settings_change(self, event=None):
        if hasattr(self, '_presenter_update_job'): self.root.after_cancel(self._presenter_update_job)
        self._presenter_update_job = self.root.after(150, self._schedule_presenter_preview_update)

    def _schedule_presenter_preview_update(self):
        video_path = self.presenter_video_path_var.get()
        is_enabled = bool(video_path and os.path.exists(video_path))
        if not is_enabled:
            self.presenter_preview.update_preview(is_enabled=False)
            return
        settings = {'chroma_enabled': self.presenter_chroma_enabled_var.get(), 'chroma_color': self.presenter_chroma_color_var.get(),
                    'chroma_similarity': self.presenter_chroma_similarity_var.get(), 'chroma_blend': self.presenter_chroma_blend_var.get()}
        self.thread_executor.submit(self._process_presenter_frame_for_preview, settings)

    def _process_presenter_frame_for_preview(self, settings: dict):
        video_path = self.presenter_video_path_var.get()
        ffmpeg_path = self.ffmpeg_path_var.get()
        if not (video_path and os.path.isfile(video_path) and os.path.isfile(ffmpeg_path)): return
        try:
            self.root.update_idletasks()
            preview_h = self.presenter_preview.winfo_height()
            if preview_h < 10: preview_h = 240
            target_h = max(64, int(preview_h * float(self.presenter_scale_var.get())))
            vf_parts = [f"scale=w=-1:h={target_h}"]
            if settings.get('chroma_enabled'):
                raw_sim = max(0.0, min(float(settings.get('chroma_similarity', 0.20)), 1.0))
                raw_smth = max(0.0, min(float(settings.get('chroma_blend', 0.10)), 1.0))
                sim = 0.05 + 0.45 * raw_sim
                smth = 0.02 + 0.28 * raw_smth
                key_hex = settings.get('chroma_color', '#00FF00').replace('#', '0x')
                vf_parts.append(f"format=rgba,chromakey={key_hex}:{sim}:{smth}")
            vf = ",".join(vf_parts)
            out_png = os.path.join(tempfile.gettempdir(), f"presenter_preview_{int(time.time())}.png")
            cmd = [ffmpeg_path, "-y", "-i", video_path, "-vf", vf, "-frames:v", "1", out_png]
            creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            subprocess.run(cmd, check=True, creationflags=creation_flags, capture_output=True, timeout=15)
            if os.path.exists(out_png):
                if self.presenter_processed_frame_path and self.presenter_processed_frame_path != out_png and os.path.exists(self.presenter_processed_frame_path):
                    try: os.remove(self.presenter_processed_frame_path)
                    except OSError: pass
                self.presenter_processed_frame_path = out_png
                self.progress_queue.put(("update_presenter_preview", out_png))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, Exception) as e:
            logger.error(f"Falha ao gerar o frame de preview do apresentador: {e}", exc_info=True)
            self.progress_queue.put(("update_presenter_preview_error", "Erro ao gerar preview"))

    def _update_presenter_preview_from_queue(self, image_path=None, error_message=None):
        if not hasattr(self, 'presenter_preview'): return
        self.presenter_preview.update_preview(
            image_path=image_path, position_key=self.presenter_position_var.get(),
            scale=self.presenter_scale_var.get(), is_enabled=bool(self.presenter_video_path_var.get()),
            error_message=error_message)

    def _create_font_size_slider(self, parent, row, col):
        ttk.Label(parent, text="Tamanho:").grid(row=row, column=col, sticky="w", padx=(0,10), pady=5)
        font_size_frame = ttk.Frame(parent)
        font_size_frame.grid(row=row, column=col+1, sticky="ew")
        font_size_frame.columnconfigure(0, weight=1)
        display_var = ttk.StringVar()
        def update_display(v):
            val = int(float(v))
            self.subtitle_fontsize_var.set(val)
            display_var.set(str(val))
            self.on_subtitle_style_change()
        ttk.Scale(font_size_frame, from_=10, to=100, variable=self.subtitle_fontsize_var, orient=HORIZONTAL, command=update_display).grid(row=0, column=0, sticky="ew", padx=(0,10))
        ttk.Label(font_size_frame, textvariable=display_var, width=3).grid(row=0, column=1)
        update_display(self.subtitle_fontsize_var.get())

    def open_log_folder(self):
        if self.log_file_path:
            log_dir = os.path.dirname(self.log_file_path)
            try:
                if platform.system() == "Windows": os.startfile(log_dir)
                elif platform.system() == "Darwin": subprocess.Popen(["open", log_dir])
                else: subprocess.Popen(["xdg-open", log_dir])
                self.update_status_textbox(f"Pasta de logs aberta: {log_dir}", tag="info")
            except Exception as e:
                logger.error(f"Não foi possível abrir a pasta de logs: {e}")
                Messagebox.show_error(f"Não foi possível abrir a pasta de logs.\nPor favor, navegue manualmente para:\n{log_dir}", "Erro", parent=self.root)
        else:
            Messagebox.show_warning("O caminho do arquivo de log ainda não foi definido.", "Aviso", parent=self.root)
            
    def _create_editor_process_section(self, parent, start_row):
        action_frame = ttk.LabelFrame(parent, text=" Editor: Ações e Progresso ", padding=15)
        action_frame.grid(row=start_row, column=0, sticky="ew", pady=(10, 10))
        action_frame.columnconfigure(1, weight=1)
        
        button_frame = ttk.Frame(action_frame)
        button_frame.grid(row=0, column=0, rowspan=2, padx=(0, 20), sticky='n')
        self.start_button = ttk.Button(button_frame, text="▶ Iniciar Edição", command=self.start_processing_controller, bootstyle="success", width=15)
        self.start_button.pack(pady=(0, 5), ipady=2)
        self.cancel_button = ttk.Button(button_frame, text="⏹ Cancelar", command=self.request_cancellation, state=DISABLED, bootstyle="danger-outline", width=15)
        self.cancel_button.pack(pady=5, ipady=2)
        
        ttk.Label(action_frame, text="Progresso do Item:").grid(row=0, column=1, sticky="w", pady=(0,5))
        self.progress_bar = ttk.Progressbar(action_frame, mode='determinate', bootstyle="success-striped")
        self.progress_bar.grid(row=0, column=2, sticky="ew", padx=10, pady=(0,5))
        
        self.batch_progress_frame = ttk.Frame(action_frame)
        self.batch_progress_frame.grid(row=1, column=1, columnspan=2, sticky="ew")
        self.batch_progress_frame.columnconfigure(1, weight=1)
        ttk.Label(self.batch_progress_frame, text="Progresso do Lote:").grid(row=0, column=0, sticky="w")
        self.batch_progress_bar = ttk.Progressbar(self.batch_progress_frame, mode='determinate', bootstyle="info-striped")
        self.batch_progress_bar.grid(row=0, column=1, sticky="ew", padx=10)

        log_frame = ttk.LabelFrame(parent, text=" Logs de Processamento (Editor) ", padding=(15, 10))
        log_frame.grid(row=start_row + 1, column=0, sticky="nsew", pady=(0, 5))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.status_text = scrolledtext.ScrolledText(log_frame, height=8, wrap=WORD, relief="flat", state=DISABLED, font=('Consolas', 9))
        self.status_text.grid(row=0, column=0, sticky="nsew")
        self.status_text.tag_configure("error", foreground=self.root.style.colors.danger)
        self.status_text.tag_configure("success", foreground=self.root.style.colors.success)
        self.status_text.tag_configure("info", foreground=self.root.style.colors.info)
        self.status_text.tag_configure("warning", foreground=self.root.style.colors.warning)
        self.status_text.tag_configure("debug", foreground=self.root.style.colors.secondary)

    def _create_status_bar(self):
        status_bar = ttk.Frame(self.root, padding=(10, 5))
        status_bar.grid(row=1, column=0, sticky="ew")
        status_bar.columnconfigure(0, weight=1)
        
        self.license_status_label = ttk.Label(status_bar, text="Verificando licença...")
        self.license_status_label.pack(side=RIGHT)
        self.update_license_status_display(self.license_data)

    def update_license_status_display(self, license_info=None):
        data_to_use = license_info or self.license_data
        if not hasattr(self, 'license_status_label'): return
        if not data_to_use or 'data' not in data_to_use:
            self.license_status_label.config(text="Licença: Inválida", bootstyle="danger"); return
        
        attributes = data_to_use['data']['attributes']
        expiry_str = attributes.get('expiry')
        if not expiry_str:
            self.license_status_label.config(text="Licença: Vitalícia", bootstyle="success"); return
        try:
            from datetime import datetime, timezone
            expiry_date = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
            remaining = expiry_date - datetime.now(timezone.utc)
            if remaining.days >= 0:
                text = f"Licença Ativa (Expira em: {remaining.days + 1} dias)"
                bootstyle = "success" if remaining.days > 7 else "warning"
            else:
                text = "Licença: Expirada"
                bootstyle = "danger"
            self.license_status_label.config(text=text, bootstyle=bootstyle)
        except Exception as e:
            logger.error(f"Erro ao calcular a expiração da licença: {e}")
            self.license_status_label.config(text="Erro na licença", bootstyle="danger")

    def _create_file_input(self, parent, row, label_text, var_key, command, hint_text: Optional[str] = None):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=4)
        frame.columnconfigure(0, weight=0, minsize=200)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=0)
        ttk.Label(frame, text=label_text, anchor='w', justify='left', wraplength=350).grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        entry = ttk.Entry(frame, textvariable=self.path_vars[var_key], state="readonly")
        entry.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        button_container = ttk.Frame(frame)
        button_container.grid(row=0, column=2, sticky='e')
        select_button = ttk.Button(
            button_container,
            text="Selecionar...",
            command=command,
            bootstyle="info-outline",
            width=12,
        )
        select_button.pack(side=LEFT)
        if hint_text:
            hint_style = "info"
            normalized_hint = hint_text.lower()
            if "⚠️" in hint_text or "necessária" in normalized_hint or "obrigatória" in normalized_hint:
                hint_style = "warning"
            ttk.Label(
                frame,
                text=hint_text,
                anchor='w',
                justify='left',
                wraplength=350,
                bootstyle=hint_style,
            ).grid(row=1, column=0, columnspan=3, sticky="w", padx=(0, 10), pady=(2, 0))
        if var_key in ['png_overlay', 'effect_overlay', 'presenter_video']:
            clear_cmd = lambda: (self.path_vars[var_key].set(''), self.on_png_settings_change() if var_key == 'png_overlay' else self.on_presenter_settings_change())
            clear_button = ttk.Button(button_container, text="Limpar", command=clear_cmd, bootstyle="danger-outline", width=8)
            clear_button.pack(side=LEFT, padx=(5, 0))
            ToolTip(clear_button, f"Remover {var_key.replace('_', ' ')}")
        return frame

    def _create_color_picker(self, parent, row, column, variable, callback=None):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=column, sticky="ew")
        entry = ttk.Entry(frame, textvariable=variable, width=10)
        if callback: entry.bind("<KeyRelease>", lambda e: callback())
        entry.pack(side=LEFT, fill=X, expand=True)
        button = ttk.Button(frame, text="🎨", width=3, bootstyle="info-outline", command=lambda: self.select_color(variable, callback))
        button.pack(side=LEFT, padx=(5,0))
        return frame

    def on_subtitle_style_change(self, event=None):
        if hasattr(self, '_subtitle_update_job'): self.root.after_cancel(self._subtitle_update_job)
        self._subtitle_update_job = self.root.after(100, self.update_subtitle_preview_job)
        
    def update_subtitle_preview_job(self):
        if not hasattr(self, 'subtitle_preview'): return
        try:
            font_size = int(self.subtitle_fontsize_var.get())
            is_bold, is_italic = self.subtitle_bold_var.get(), self.subtitle_italic_var.get()
            font_path = self.subtitle_font_file.get()
            text_color, outline_color = self.subtitle_textcolor_var.get(), self.subtitle_outlinecolor_var.get()
            position_key = self.subtitle_position_var.get()
            style_list = []
            if is_bold: style_list.append("bold")
            if is_italic: style_list.append("italic")
            font_obj = None
            try:
                if font_path and os.path.exists(font_path):
                    user_font_family = Path(font_path).stem
                    font_tuple = (user_font_family, font_size, *style_list)
                    font_obj = tkFont.Font(font=font_tuple)
                else:
                    font_tuple = ("Arial", font_size, *style_list)
                    font_obj = tkFont.Font(font=font_tuple)
            except Exception as font_error:
                logger.critical(f"ERRO CRÍTICO DE FONTE: {font_error}", exc_info=True)
                font_obj = tkFont.Font(family="Arial", size=12)
            self.subtitle_preview.update_preview(font_config=font_obj, text_color=text_color, outline_color=outline_color, position_key=position_key)
        except Exception as e:
            logger.error(f"Erro inesperado em update_subtitle_preview_job: {e}", exc_info=True)

    def update_ui_for_media_type(self, event=None):
        # ... (sem alterações) ...
        mode = self.media_type.get()
        normalized_mode = "batch_video" if mode == "batch" else mode
        is_single_video, is_slideshow = (normalized_mode == "video_single"), (normalized_mode == "image_folder")
        is_batch_video = normalized_mode == "batch_video"
        is_batch_image = normalized_mode == "batch_image"
        is_batch_hierarchical = normalized_mode == "batch_image_hierarchical"
        is_batch_mixed = normalized_mode == "batch_mixed"
        is_any_batch = is_batch_video or is_batch_image or is_batch_hierarchical or is_batch_mixed
        is_any_slideshow = is_slideshow or is_batch_image or is_batch_mixed

        frames_to_manage = {
            self.single_inputs_frame: is_single_video or is_slideshow,
            self.batch_inputs_frame: is_any_batch,
            self.batch_video_inputs_frame: is_batch_video,
            self.batch_image_inputs_frame: is_batch_image,
            self.batch_hierarchical_inputs_frame: is_batch_hierarchical,
            self.batch_mixed_inputs_frame: is_batch_mixed,
            self.music_file_frame: not is_any_batch,
            self.music_folder_frame: is_any_batch,
            self.music_behavior_frame: is_any_batch,
            self.batch_progress_frame: is_any_batch,
            self.slideshow_section: is_any_slideshow
        }

        for frame, show in frames_to_manage.items():
            if show:
                frame.grid()
            else:
                frame.grid_remove()

        if is_single_video or is_slideshow:
            label_text = "Pasta de Imagens (Slideshow) (Obrigatória):" if is_slideshow else "Arquivo de Vídeo Base (Obrigatório):"
            self.media_path_label_widget.winfo_children()[0].config(text=label_text)
        self.notebook.tab(1, text="Editor: Vídeo & Slideshow" if is_any_slideshow else "Editor: Vídeo")
        if is_batch_image or is_batch_mixed: self.video_settings_section.grid_remove()
        else: self.video_settings_section.grid()

    def select_media_single(self):
        # ... (sem alterações) ...
        if self.media_type.get() == "image_folder":
            self.select_folder('media_single', "Selecione a Pasta de Imagens (Slideshow)")
        else:
            self.select_file('media_single', "Selecione o Arquivo de Vídeo Base", SUPPORTED_VIDEO_FT)

    def select_file(self, var_key, title, filetypes, callback=None):
        # ... (sem alterações) ...
        variable = self.path_vars[var_key]
        last_dir_key_map = {'png_overlay': 'last_png_folder', 'effect_overlay': 'last_effect_folder', 'presenter_video': 'last_presenter_folder'}
        last_dir_key = last_dir_key_map.get(var_key, 'output_folder')
        last_dir = os.path.dirname(variable.get()) if variable.get() else self.config.get(last_dir_key)
        filepath = filedialog.askopenfilename(title=title, filetypes=filetypes, initialdir=last_dir, parent=self.root)
        if filepath:
            variable.set(filepath)
            if var_key == 'subtitle_font': self.load_font_resource(filepath)
            elif var_key in last_dir_key_map: self.config[last_dir_key_map[var_key]] = os.path.dirname(filepath)
            if callback: callback()

    def reset_subtitle_font(self):
        # ... (sem alterações) ...
        logger.info("Resetando para a fonte padrão.")
        self.unload_all_font_resources()
        self.subtitle_font_file.set('')
        self.on_subtitle_style_change()

    def load_font_resource(self, filepath: str):
        # ... (sem alterações) ...
        if platform.system() != "Windows": return
        self.unload_all_font_resources()
        gdi32 = ctypes.WinDLL('gdi32')
        if gdi32.AddFontResourceW(filepath) > 0:
            self.loaded_fonts.append(filepath)
            logger.info(f"Fonte '{filepath}' carregada com sucesso.")
        else:
            logger.error(f"Falha ao carregar a fonte '{filepath}'.")
            Messagebox.show_error(f"O Windows não conseguiu carregar a fonte:\n{filepath}", "Erro de Fonte")
            
    def unload_all_font_resources(self):
        # ... (sem alterações) ...
        if platform.system() != "Windows" or not self.loaded_fonts: return
        gdi32 = ctypes.WinDLL('gdi32')
        for font_path in self.loaded_fonts:
            if gdi32.RemoveFontResourceW(font_path) > 0: logger.info(f"Fonte '{font_path}' descarregada.")
            else: logger.warning(f"Falha ao descarregar a fonte '{font_path}'.")
        self.loaded_fonts.clear()

    def select_folder(self, var_key, title):
        # ... (sem alterações) ...
        variable = self.path_vars[var_key]
        last_dir_key_map = {'output': 'output_folder', 'batch_image': 'last_image_folder', 'batch_root': 'last_root_folder', 'batch_mixed_media_folder': 'last_mixed_folder'}
        last_dir_key = last_dir_key_map.get(var_key, 'output_folder')
        last_dir = variable.get() or self.config.get(last_dir_key)
        folderpath = filedialog.askdirectory(title=title, initialdir=last_dir, parent=self.root)
        if folderpath:
            variable.set(folderpath)
            if var_key in last_dir_key_map: self.config[last_dir_key_map[var_key]] = folderpath

    def select_color(self, variable, callback=None):
        # ... (sem alterações) ...
        try:
            color = colorchooser.askcolor(title="Escolha uma cor", initialcolor=variable.get(), parent=self.root)
        except Exception as exc:
            logger.error("Falha ao abrir seletor de cores: %s", exc, exc_info=True)
            Messagebox.show_error("Não foi possível abrir o seletor de cores.", "Erro", parent=self.root)
            return
        if color and color[1]:
            variable.set(color[1].upper())
            if callback: callback()

    def install_ffmpeg_automatically(self):
        # ... (sem alterações) ...
        if platform.system() != "Windows": Messagebox.show_info("A instalação automática só é suportada no Windows.", "Info", parent=self.root); return
        if self.is_processing: Messagebox.show_warning("Aguarde o término do processamento atual.", "Aviso", parent=self.root); return
        if not Messagebox.yesno("Isso irá baixar o FFmpeg (aproximadamente 80MB) da internet. Deseja continuar?", "Instalar FFmpeg", parent=self.root): return
        threading.Thread(target=self._installation_thread_worker, daemon=True).start()

    def _installation_thread_worker(self):
        # ... (sem alterações) ...
        self.progress_queue.put(("status", "Iniciando download do FFmpeg...", "info"))
        try:
            ffmpeg_dir = Path.cwd() / "ffmpeg"; ffmpeg_dir.mkdir(exist_ok=True)
            if (ffmpeg_dir / "bin" / "ffmpeg.exe").exists():
                self.progress_queue.put(("status", "FFmpeg já parece estar instalado localmente.", "info"))
                self.ffmpeg_path_var.set(str((ffmpeg_dir / "bin" / "ffmpeg.exe").resolve())); return
            url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
            zip_path = ffmpeg_dir / "ffmpeg.zip"
            with urllib.request.urlopen(url) as response, open(zip_path, 'wb') as out_file:
                 total_size = int(response.info().get('Content-Length', 0)); chunk_size = 8192; downloaded = 0
                 while True:
                     chunk = response.read(chunk_size)
                     if not chunk: break
                     out_file.write(chunk); downloaded += len(chunk)
                     if total_size > 0: self.progress_queue.put(("status", f"Baixando FFmpeg... {int((downloaded/total_size)*100)}%", "info"))
            self.progress_queue.put(("status", "Download completo. Extraindo...", "info"))
            with zipfile.ZipFile(zip_path, 'r') as zip_ref: zip_ref.extractall(ffmpeg_dir)
            zip_path.unlink()
            found_exe = next(ffmpeg_dir.glob("**/bin/ffmpeg.exe"), None)
            if found_exe:
                self.ffmpeg_path_var.set(str(found_exe.resolve()))
                self.progress_queue.put(("messagebox", "info", "Sucesso", "FFmpeg instalado com sucesso!"))
            else: raise FileNotFoundError("ffmpeg.exe não encontrado no ficheiro baixado.")
        except Exception as e:
            logger.error(f"Falha na instalação do FFmpeg: {e}", exc_info=True)
            self.progress_queue.put(("messagebox", "error", "Erro na Instalação", f"Falha ao instalar o FFmpeg: {e}"))
        finally: self.progress_queue.put(("ffmpeg_check",))

    def find_ffmpeg_on_startup(self):
        # ... (sem alterações) ...
        path_to_use = ""
        local_ffmpeg = next(Path.cwd().glob("ffmpeg/bin/ffmpeg.exe"), None)
        configured_path = self.ffmpeg_path_var.get()
        path_from_env = FFmpegManager.find_executable()
        if local_ffmpeg and local_ffmpeg.is_file(): path_to_use = str(local_ffmpeg.resolve())
        elif configured_path and os.path.isfile(configured_path): path_to_use = configured_path
        elif path_from_env: path_to_use = path_from_env
        self.ffmpeg_path_var.set(path_to_use)
        logger.info(f"Usando FFmpeg de: {path_to_use or 'Nenhum encontrado'}")
        self.update_ffmpeg_status()

    def update_ffmpeg_status(self):
        # ... (sem alterações) ...
        path = self.ffmpeg_path_var.get()
        is_ok = path and os.path.isfile(path)
        self.ffmpeg_status_label.config(text=f"FFmpeg OK: {Path(path).name}" if is_ok else "FFmpeg Não encontrado", bootstyle="success" if is_ok else "danger")
        if is_ok: self._check_available_encoders()
        else:
            self.available_encoders_cache = []
            if hasattr(self, 'video_codec_combobox'):
                self.video_codec_combobox.config(values=["Automático", "CPU (libx264)"])
            self.update_gpu_status(set())
        self._downloader_check_readiness()
            
    def ask_ffmpeg_path_manual(self):
        # ... (sem alterações) ...
        filetypes = [("Executáveis", "*.exe"), ("Todos", "*.*")] if platform.system() == "Windows" else [("Todos", "*")]
        filepath = filedialog.askopenfilename(title="Selecione o executável do FFmpeg", filetypes=filetypes, parent=self.root)
        if filepath and "ffmpeg" in os.path.basename(filepath).lower(): self.ffmpeg_path_var.set(filepath)
        elif filepath: Messagebox.show_error("Este não parece ser um executável FFmpeg válido.", "Erro", parent=self.root)
        self.update_ffmpeg_status()

    def _check_available_encoders(self):
        # ... (sem alterações) ...
        self.available_encoders_cache = FFmpegManager.check_encoders(self.ffmpeg_path_var.get())
        encoder_friendly_names = {
            "h264_nvenc": ("nvidia", "GPU (NVIDIA NVENC H.264)"),
            "hevc_nvenc": ("nvidia", "GPU (NVIDIA NVENC HEVC)"),
            "av1_nvenc": ("nvidia", "GPU (NVIDIA NVENC AV1)"),
            "h264_qsv": ("intel", "GPU (Intel QSV H.264)"),
            "hevc_qsv": ("intel", "GPU (Intel QSV HEVC)"),
            "av1_qsv": ("intel", "GPU (Intel QSV AV1)"),
            "h264_amf": ("amd", "GPU (AMD AMF H.264)"),
            "hevc_amf": ("amd", "GPU (AMD AMF HEVC)"),
            "av1_amf": ("amd", "GPU (AMD AMF AV1)"),
            "h264_vaapi": ("vaapi", "GPU (VAAPI H.264)"),
            "hevc_vaapi": ("vaapi", "GPU (VAAPI HEVC)"),
            "av1_vaapi": ("vaapi", "GPU (VAAPI AV1)"),
        }
        options = ["Automático", "CPU (libx264)"]
        detected_hardware: Set[str] = set()
        for encoder_name, (hardware_key, friendly_label) in encoder_friendly_names.items():
            if encoder_name in self.available_encoders_cache:
                options.append(friendly_label)
                detected_hardware.add(hardware_key)
        if hasattr(self, 'video_codec_combobox'):
            self.video_codec_combobox.config(values=options)
            if self.video_codec_var.get() not in options: self.video_codec_var.set("Automático")
        self.update_gpu_status(detected_hardware)

    def update_gpu_status(self, hardware_support: Optional[Set[str]] = None):
        # ... (sem alterações) ...
        if not hasattr(self, 'gpu_status_label'):
            return
        hardware_support = hardware_support or set()
        if hardware_support:
            status_lines = []
            if "nvidia" in hardware_support:
                status_lines.append("✓ NVIDIA NVENC disponível")
            if "intel" in hardware_support:
                status_lines.append("✓ Intel Quick Sync Video disponível")
            if "amd" in hardware_support:
                status_lines.append("✓ AMD AMF disponível")
            if "vaapi" in hardware_support:
                status_lines.append("✓ Aceleração VAAPI disponível")
            status_text = "\n".join(status_lines)
            bootstyle = "success"
        else:
            status_text = "⚠️ Nenhuma placa de vídeo com aceleração detetada (usando CPU)."
            bootstyle = "warning"
        self.gpu_status_label.config(text=status_text, bootstyle=bootstyle)

    def validate_inputs(self) -> bool:
        # ... (sem alterações) ...
        logger.info("Validando entradas do editor...")
        if not self.ffmpeg_path_var.get() or not os.path.isfile(self.ffmpeg_path_var.get()):
            Messagebox.show_error("Caminho do FFmpeg inválido. Verifique o caminho na aba 'Configurações'.", "Erro de Configuração", parent=self.root); self.notebook.select(self.notebook.tabs()[-1]); return False
        if not self.output_folder.get() or not os.path.isdir(self.output_folder.get()):
            Messagebox.show_error("Pasta de saída inválida.", "Erro de Saída", parent=self.root); return False
        mode = self.media_type.get()
        if mode == "video_single" and not os.path.isfile(self.media_path_single.get()): Messagebox.show_error("Arquivo de Vídeo Base inválido.", "Erro de Entrada", parent=self.root); return False
        if mode == "image_folder" and not os.path.isdir(self.media_path_single.get()): Messagebox.show_error("Pasta de Imagens (Slideshow) inválida.", "Erro de Entrada", parent=self.root); return False
        if mode == "batch_video" and (not os.path.isdir(self.batch_video_parent_folder.get()) or not os.path.isdir(self.batch_audio_folder.get())): Messagebox.show_error("As pastas de Vídeos Base e de Narrações (Áudio) devem ser válidas para o lote de vídeos.", "Erro de Entrada", parent=self.root); return False
        if mode == "batch_image" and (not os.path.isdir(self.batch_image_parent_folder.get()) or not os.path.isdir(self.batch_audio_folder.get())): Messagebox.show_error("As pastas de Imagens Base e de Narrações (Áudio) devem ser válidas para o lote de imagens.", "Erro de Entrada", parent=self.root); return False
        if mode == "batch_mixed" and (not os.path.isdir(self.batch_mixed_media_folder.get()) or not os.path.isdir(self.batch_audio_folder.get())): Messagebox.show_error("As pastas de Mídia Base e de Narrações (Áudio) devem ser válidas para o lote misto.", "Erro de Entrada", parent=self.root); return False
        if mode == "batch_image_hierarchical" and (not os.path.isdir(self.batch_root_folder.get()) or not os.path.isdir(self.batch_image_parent_folder.get())): Messagebox.show_error("As pastas Raiz do Lote e a Biblioteca de Vídeos/Imagens devem ser válidas para o lote hierárquico.", "Erro de Entrada", parent=self.root); return False
        logger.info("Entradas do editor validadas com sucesso."); return True

    def start_processing_controller(self):
        # ... (sem alterações) ...
        if self.is_processing: Messagebox.show_warning("Um processamento já está em andamento.", "Aviso", parent=self.root); return
        if not self.validate_inputs(): return
        if video_processing_logic is None: Messagebox.show_error("O módulo 'video_processing_logic.py' não foi encontrado.", "Erro Crítico", parent=self.root); return
        self.is_processing = True
        self.cancel_requested.clear()
        self.start_button.config(state=DISABLED)
        self.cancel_button.config(state=NORMAL)
        self.progress_bar['value'] = 0
        self.batch_progress_bar['value'] = 0
        self.progress_bar.config(bootstyle="success-striped")
        self.batch_progress_bar.config(bootstyle="info-striped")
        self.update_status_textbox("Iniciando processamento do editor...", append=False, tag="info")
        params = self._gather_processing_params()
        future = self.thread_executor.submit(video_processing_logic.process_entrypoint, params, self.progress_queue, self.cancel_requested)
        future.add_done_callback(self._processing_thread_done_callback)

    def _gather_processing_params(self) -> Dict[str, Any]:
        # ... (sem alterações) ...
        params = {var_name.replace("_var", ""): var_obj.get() for var_name, var_obj in self.__dict__.items() if isinstance(var_obj, (tk.Variable, tk.StringVar))}
        for key, path_val in params.items():
            if isinstance(path_val, str) and path_val and ("_path" in key or "_folder" in key or "_file" in key):
                params[key] = os.path.normpath(os.path.abspath(path_val))
        params['slideshow_transition'] = SLIDESHOW_TRANSITIONS.get(self.transition_name_var.get(), 'fade')
        params['available_encoders'] = self.available_encoders_cache
        params.pop('single_language_display', None)
        try:
            slider_font_size = int(self.subtitle_fontsize_var.get())
            res_str = params.get('resolution') or self.resolution_var.get()
            video_height = int(re.search(r'(\d+)x(\d+)', res_str).group(2)) if res_str and re.search(r'(\d+)x(\d+)', res_str) else None
            self.root.update_idletasks()
            preview_height = self.subtitle_preview.winfo_height() if hasattr(self, 'subtitle_preview') and self.subtitle_preview else None
            if video_height and preview_height and preview_height >= 10:
                adjusted_font_size = max(1, int(round(slider_font_size * (video_height / float(preview_height)))))
            else:
                adjusted_font_size = slider_font_size
        except Exception:
            adjusted_font_size = int(self.subtitle_fontsize_var.get())
        params['subtitle_style'] = {'fontsize': adjusted_font_size, 'text_color': self.subtitle_textcolor_var.get(), 'outline_color': self.subtitle_outlinecolor_var.get(),
                                   'bold': self.subtitle_bold_var.get(), 'italic': self.subtitle_italic_var.get(), 'position': self.subtitle_position_var.get(),
                                   'font_file': self.subtitle_font_file.get(), 'position_map': SUBTITLE_POSITIONS}
        params['effect_blend_mode'] = EFFECT_BLEND_MODES.get(self.effect_blend_mode_var.get(), 'screen')
        params['intro_enabled'] = self.intro_enabled_var.get()
        single_language_code = self.single_language_code_var.get()
        if isinstance(single_language_code, str) and single_language_code.lower() != 'auto':
            single_language_code = single_language_code.upper()
        else:
            single_language_code = 'auto'
        params['single_language_code'] = single_language_code
        params['intro_phrase_enabled'] = False
        params['show_tech_logs'] = self.show_tech_logs_var.get()
        intro_default_text = self.intro_default_text_var.get()
        if hasattr(self, 'intro_default_text_widget'):
            default_state = self.intro_default_text_widget.cget("state")
            if default_state == 'disabled':
                self.intro_default_text_widget.configure(state=NORMAL)
            intro_default_text = self.intro_default_text_widget.get("1.0", "end").strip()
            if default_state == 'disabled':
                self.intro_default_text_widget.configure(state=DISABLED)
        params['intro_default_text'] = intro_default_text.strip()
        params['intro_language_code'] = self.intro_language_var.get()
        params['intro_texts'] = self._collect_intro_texts()
        params['intro_font_choice'] = self.intro_font_choice_var.get()
        params['intro_font_bold'] = self.intro_font_bold_var.get()
        typing_duration_value = int(self.intro_typing_duration_seconds_var.get() or 10)
        if typing_duration_value not in {10, 15, 20, 30}:
            typing_duration_value = 10
        params['intro_typing_duration_seconds'] = typing_duration_value
        hold_duration_value = int(self.intro_hold_duration_seconds_var.get() or 2)
        if hold_duration_value <= 0:
            hold_duration_value = 2
        params['intro_hold_duration_seconds'] = hold_duration_value
        banner_default_text = self.banner_default_text_var.get()
        if hasattr(self, 'banner_default_text_widget'):
            banner_state = self.banner_default_text_widget.cget("state")
            if banner_state == 'disabled':
                self.banner_default_text_widget.configure(state=NORMAL)
            banner_default_text = self.banner_default_text_widget.get("1.0", "end").strip()
            if banner_state == 'disabled':
                self.banner_default_text_widget.configure(state=DISABLED)
        params['banner_enabled'] = self.banner_enabled_var.get()
        params['banner_default_text'] = banner_default_text.strip()
        params['banner_language_code'] = self.banner_language_code_var.get()
        params['banner_use_gradient'] = self.banner_use_gradient_var.get()
        params['banner_solid_color'] = self.banner_solid_color_var.get()
        params['banner_gradient_start'] = self.banner_gradient_start_var.get()
        params['banner_gradient_end'] = self.banner_gradient_end_var.get()
        params['banner_font_color'] = self.banner_font_color_var.get()
        params['banner_height_ratio'] = float(self.banner_height_ratio_var.get())
        params['banner_font_scale'] = float(self.banner_font_scale_var.get())
        params['banner_outline_enabled'] = self.banner_outline_enabled_var.get()
        params['banner_outline_color'] = self.banner_outline_color_var.get()
        params['banner_outline_offset'] = float(self.banner_outline_offset_var.get())
        params['banner_shadow_enabled'] = self.banner_shadow_enabled_var.get()
        params['banner_shadow_color'] = self.banner_shadow_color_var.get()
        params['banner_shadow_offset_x'] = float(self.banner_shadow_offset_x_var.get())
        params['banner_shadow_offset_y'] = float(self.banner_shadow_offset_y_var.get())
        params['banner_duration'] = float(self.banner_duration_var.get())
        params['banner_texts'] = {}
        logger.debug(f"Parâmetros finais coletados: {json.dumps(params, indent=2, default=str)}")
        return params

    def request_cancellation(self):
        # ... (sem alterações) ...
        if self.is_processing:
            logger.info("Cancelamento solicitado pelo usuário.")
            self.cancel_requested.set()
            self.cancel_button.config(state=DISABLED)
            self.update_status_textbox("Cancelamento solicitado... Aguardando a tarefa terminar.", tag="warning")

    def _processing_thread_done_callback(self, future):
        # ... (sem alterações) ...
        try: future.result()
        except Exception as e:
            logger.error(f"Exceção na thread de processamento: {e}", exc_info=True)
            self.progress_queue.put(("status", f"Erro fatal na thread: {e}", "error"))
        finally:
            self.progress_queue.put(("finish", False))

    def _finalize_processing_ui_state(self, success: bool):
        # ... (sem alterações) ...
        self.is_processing = False
        self.start_button.config(state=NORMAL)
        self.cancel_button.config(state=DISABLED)
        final_style = "success" if success else "danger"
        self.progress_bar.config(bootstyle=final_style)
        self.batch_progress_bar.config(bootstyle=f"info-{final_style}")

    def _downloader_log(self, message):
        # ... (sem alterações) ...
        self.progress_queue.put(("downloader_log", message))

    def _downloader_update_ui(self, widget_name, config):
        # ... (sem alterações) ...
        self.progress_queue.put(("downloader_ui", widget_name, config))

    def _downloader_initialize_systems(self):
        # ... (sem alterações) ...
        self.downloader_button.configure(state="disabled", text="Inicializando Motor...")
        self.downloader_engine_status_label.config(text="Verificando motor de download...", bootstyle="warning")
        self.thread_executor.submit(self._downloader_update_engine)

    def _downloader_update_engine(self):
        # ... (sem alterações) ...
        try:
            self._downloader_log("Verificando atualizações do motor de download (yt-dlp)...")
            self.progress_queue.put(("downloader_engine_status", "Verificando motor...", "warning"))

            engine_filename = "yt-dlp.exe" if platform.system() == "Windows" else "yt-dlp"
            engine_path_in_appdata = os.path.join(APP_DATA_PATH, engine_filename)

            try:
                self._downloader_log("Procurando a versão mais recente do yt-dlp no GitHub...")
                api_url = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
                response = requests.get(api_url, timeout=15)
                response.raise_for_status()
                release_data = response.json()
                download_url = next((asset.get("browser_download_url") for asset in release_data.get("assets", []) if asset.get("name") == engine_filename), None)
                
                if not download_url:
                    raise Exception(f"Não foi possível encontrar o arquivo '{engine_filename}' na versão mais recente.")
                
                self._downloader_log(f"Baixando motor de: {download_url}")
                self.progress_queue.put(("downloader_engine_status", "Baixando motor...", "info"))
                
                with requests.get(download_url, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    with open(engine_path_in_appdata, 'wb') as f:
                        shutil.copyfileobj(r.raw, f)

                self.yt_dlp_engine_path = engine_path_in_appdata
                self._downloader_log(f"Motor de download atualizado com sucesso em: {self.yt_dlp_engine_path}")
                self.progress_queue.put(("downloader_engine_status", "Motor de Download OK", "success"))

            except Exception as e:
                self._downloader_log(f"ERRO ao baixar/atualizar motor: {e}. Verificando alternativas...")
                if os.path.exists(engine_path_in_appdata):
                    self.yt_dlp_engine_path = engine_path_in_appdata
                    self._downloader_log(f"AVISO: Falha na atualização. Usando a versão local existente em: {self.yt_dlp_engine_path}")
                    self.progress_queue.put(("downloader_engine_status", "Motor OK (local)", "success"))
                else:
                    self._downloader_log("Tentando encontrar yt-dlp no PATH do sistema...")
                    path_in_system = shutil.which('yt-dlp')
                    if path_in_system:
                        self.yt_dlp_engine_path = path_in_system
                        self._downloader_log(f"Motor de download encontrado no PATH do sistema: {self.yt_dlp_engine_path}")
                        self.progress_queue.put(("downloader_engine_status", "Motor OK (sistema)", "success"))
                    else:
                        self.yt_dlp_engine_path = None
                        self._downloader_log("FALHA CRÍTICA: Motor de download não foi encontrado ou baixado.")
                        self.progress_queue.put(("downloader_engine_status", "Motor de download falhou!", "danger"))
        finally:
            self.progress_queue.put(("downloader_init_finished",))

    def _downloader_check_readiness(self):
        # ... (sem alterações) ...
        if not hasattr(self, 'downloader_button'): return 
        ffmpeg_ok = self.ffmpeg_path_var.get() and os.path.exists(self.ffmpeg_path_var.get())
        ytdlp_ok = self.yt_dlp_engine_path and os.path.exists(self.yt_dlp_engine_path)
        
        if ffmpeg_ok and ytdlp_ok:
            self.downloader_button.configure(state="normal", text="Baixar Vídeos em Lote")
            self.downloader_status_label.configure(text="Pronto para baixar.", bootstyle="success")
        else:
            self.downloader_button.configure(state="disabled", text="Verifique as Configurações")
            error_msg = []
            if not ffmpeg_ok: error_msg.append("FFmpeg não encontrado!")
            if not ytdlp_ok: error_msg.append("Motor de download falhou!")
            self.downloader_status_label.configure(text=" ".join(error_msg), bootstyle="danger")

    def _downloader_select_folder(self):
        # ... (sem alterações) ...
        folder_path = filedialog.askdirectory(initialdir=self.download_output_path_var.get(), parent=self.root)
        if folder_path:
            self.download_output_path_var.set(folder_path)
            self.config['last_download_folder'] = folder_path
            display_path = str(folder_path)
            if len(display_path) > 70: display_path = "..." + display_path[-67:]
            self.downloader_folder_label.configure(text=f"Salvar em: {display_path}")

    def _downloader_start_thread(self):
        # ... (sem alterações) ...
        if self.download_thread and self.download_thread.is_alive():
            self._downloader_log("AVISO: Um processo de download já está em andamento."); return
        self.downloader_button.configure(state="disabled", text="Baixando...")
        self.downloader_log_textbox.configure(state="normal"); self.downloader_log_textbox.delete("1.0", "end"); self.downloader_log_textbox.configure(state="disabled")
        self.download_thread = threading.Thread(target=self._downloader_run_batch, daemon=True); self.download_thread.start()

    def _downloader_on_playlist_toggle(self):
        enabled = bool(self.download_playlist_enabled_var.get())
        if hasattr(self, "download_playlist_items_combobox"):
            state = "normal" if enabled else "disabled"
            try:
                self.download_playlist_items_combobox.configure(state=state)
            except tk.TclError:
                # Defensive: combobox may not be fully initialized during tests
                pass

    def _downloader_estimate_entries(self, url: str, playlist_enabled: bool, playlist_items: str) -> int:
        if not playlist_enabled:
            return 1

        options: Dict[str, Any] = {
            "quiet": True,
            "skip_download": True,
            "no_warnings": True,
        }
        if playlist_items:
            options["playlist_items"] = playlist_items

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:
            self._downloader_log(
                f"AVISO: Não foi possível estimar a quantidade de itens da playlist ({exc}). Considerando apenas 1 vídeo."
            )
            return 1

        entries = info.get("entries") if isinstance(info, dict) else None
        if not entries:
            return 1

        try:
            count = len(entries)
        except TypeError:
            count = 0
            for _ in entries:
                count += 1

        return max(1, count)

    def _downloader_parse_percent(self, value: Optional[str]) -> Optional[float]:
        if not value:
            return None
        value = value.strip().replace('%', '')
        try:
            return max(0.0, min(float(value) / 100.0, 1.0))
        except ValueError:
            return None

    def _downloader_increment_overall(self, amount: int = 1) -> None:
        if amount <= 0:
            return
        total = getattr(self, '_downloader_overall_total', 0)
        if total <= 0:
            return
        completed = getattr(self, '_downloader_overall_completed', 0) + amount
        completed = min(completed, total)
        self._downloader_overall_completed = completed
        progress_value = completed / total
        self._downloader_update_ui('overall_progress', {'value': progress_value})
        self._downloader_update_ui('overall_status', {'text': f"{completed}/{total} concluídos"})

    def _downloader_run_batch(self):
        urls = [
            url.strip()
            for url in self.downloader_url_textbox.get('1.0', 'end').splitlines()
            if url.strip() and re.match(r"https?://", url)
        ]
        if not urls:
            self._downloader_log('ERRO: Nenhuma URL válida foi fornecida.')
            self.progress_queue.put(('downloader_finished',))
            return

        playlist_enabled = bool(self.download_playlist_enabled_var.get())
        playlist_items = (self.download_playlist_items_var.get() or '').strip()

        estimated_counts: List[int] = []
        total_expected = 0
        for url in urls:
            count = self._downloader_estimate_entries(url, playlist_enabled, playlist_items)
            estimated_counts.append(count)
            total_expected += count

        if total_expected <= 0:
            total_expected = len(urls)

        self._downloader_overall_total = max(1, total_expected)
        self._downloader_overall_completed = 0

        self._downloader_log(
            f"======= INICIANDO LOTE DE {total_expected} ITEM(NS) DISTRIBUÍDOS EM {len(urls)} LINK(S) ======="
        )
        self._downloader_update_ui('overall_progress', {'value': 0})
        self._downloader_update_ui('overall_status', {'text': f"0/{self._downloader_overall_total} concluídos"})

        for index, url in enumerate(urls):
            expected_for_link = max(1, estimated_counts[index])
            status_parts = [f"Processando link {index + 1} de {len(urls)}"]
            if expected_for_link > 1:
                status_parts.append(f"({expected_for_link} vídeos previstos)")
            else:
                status_parts.append('(1 vídeo previsto)')
            self._downloader_update_ui('status', {'text': ' '.join(status_parts), 'bootstyle': 'info'})

            try:
                self._downloader_download_single_video(
                    url,
                    expected_entries=expected_for_link,
                    link_index=index + 1,
                    total_links=len(urls),
                )
            except Exception as e:
                self._downloader_log(f"ERRO IRRECUPERÁVEL no link '{url}': {e}")
                self._downloader_update_ui('status', {'text': f"Falha ao baixar: {url}", 'bootstyle': 'danger'})

        self._downloader_log('======= LOTE CONCLUÍDO =======')
        total = max(1, getattr(self, '_downloader_overall_total', 1))
        completed = min(total, getattr(self, '_downloader_overall_completed', 0))
        self._downloader_update_ui('overall_progress', {'value': completed / total})
        self._downloader_update_ui('overall_status', {'text': f"{completed}/{total} concluídos"})
        self._downloader_update_ui('status', {'text': '✨ Todos os downloads foram concluídos!', 'bootstyle': 'success'})
        self.progress_queue.put(('downloader_finished',))

    def _downloader_download_single_video(
        self,
        url: str,
        expected_entries: int = 1,
        link_index: int = 1,
        total_links: int = 1,
    ) -> None:
        playlist_enabled = bool(self.download_playlist_enabled_var.get())
        playlist_items = (self.download_playlist_items_var.get() or '').strip()
        expected_entries = max(1, expected_entries)

        display_url = url if len(url) <= 60 else f"{url[:57]}..."
        self._downloader_update_ui(
            'status',
            {
                'text': f"Analisando link {link_index}/{total_links}: {display_url}",
                'bootstyle': 'info',
            },
        )
        self._downloader_update_ui('progress', {'value': 0, 'mode': 'indeterminate'})
        self._downloader_log(f"\n--- Processando: {url} ---")

        output_template = os.path.join(
            self.download_output_path_var.get(),
            '%(title)s [%(id)s].%(ext)s',
        )

        command: List[str] = [
            self.yt_dlp_engine_path,
            url,
            '--ffmpeg-location',
            self.ffmpeg_path_var.get(),
            '--windows-filenames',
            '-o',
            output_template,
            '--concurrent-fragments',
            '16',
            '--no-warnings',
            '--embed-thumbnail',
            '--newline',
            '--progress-template',
            'download:{"type":"%(progress._type)s","status":"%(progress._status)s","percent":"%(progress._percent_str)s","eta":"%(progress._eta_str)s","index":"%(playlist_index)s","count":"%(playlist_count)s"}',
        ]

        if playlist_enabled:
            command.append('--yes-playlist')
            if playlist_items and playlist_items.lower() not in {'todos', 'tudo'}:
                command.extend(['--playlist-items', playlist_items])
        else:
            command.append('--no-playlist')

        if self.download_format_var.get() == 'MP4':
            command.extend([
                '-f',
                'bestvideo[vcodec^=avc]+bestaudio[ext=m4a]/bestvideo[vcodec^=h264]+bestaudio/best[ext=mp4]/best',
                '--merge-output-format',
                'mp4',
            ])
        else:
            command.extend(['-f', 'bestaudio/best', '-x', '--audio-format', 'mp3', '--audio-quality', '0'])

        creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            creationflags=creationflags,
        )

        self._downloader_log(f"Executando comando: {' '.join(command)}")

        completed_ids: Set[str] = set()
        fallback_index = 0

        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            if not line:
                continue

            try:
                progress_data = json.loads(line)
            except json.JSONDecodeError:
                self._downloader_log(line)
                match = re.search(r'\[download\]\s+([\d\.]+)% of.*ETA ([\d:]+)', line)
                if match:
                    progress = float(match.group(1)) / 100
                    eta = match.group(2)
                    self._downloader_update_ui('progress', {'value': progress, 'mode': 'determinate'})
                    self._downloader_update_ui(
                        'status',
                        {'text': f"Baixando... {progress*100:.1f}% (ETA: {eta})", 'bootstyle': 'info'},
                    )
                continue

            if not isinstance(progress_data, dict) or progress_data.get('type') != 'download':
                continue

            status = progress_data.get('status')
            percent = self._downloader_parse_percent(progress_data.get('percent'))
            eta = progress_data.get('eta') or ''

            if status == 'downloading' and percent is not None:
                eta_text = eta if eta and eta.upper() != 'NA' else 'calculando...'
                self._downloader_update_ui('progress', {'value': percent, 'mode': 'determinate'})
                self._downloader_update_ui(
                    'status',
                    {'text': f"Baixando... {percent*100:.1f}% (ETA: {eta_text})", 'bootstyle': 'info'},
                )
            elif status == 'finished':
                playlist_index = progress_data.get('index') or ''
                if not playlist_index or playlist_index == 'NA':
                    playlist_index = f'single_{fallback_index}'
                    fallback_index += 1
                if playlist_index not in completed_ids:
                    completed_ids.add(playlist_index)
                    self._downloader_log(f"Item concluído (índice {playlist_index}).")
                    self._downloader_update_ui('progress', {'value': 1, 'mode': 'determinate'})
                    self._downloader_update_ui('status', {'text': 'Item concluído!', 'bootstyle': 'success'})
                    self._downloader_increment_overall(1)

        process.wait()
        process.stdout.close()

        completed_count = len(completed_ids)
        if process.returncode == 0:
            remaining = max(0, expected_entries - completed_count)
            if remaining:
                self._downloader_increment_overall(remaining)
            self._downloader_log('--- Download concluído com sucesso. ---')
            self._downloader_update_ui('status', {'text': 'Download Concluído!', 'bootstyle': 'success'})
            self._downloader_update_ui('progress', {'value': 1, 'mode': 'determinate'})
        else:
            self._downloader_log(
                f"ERRO: O processo de download falhou com o código de saída {process.returncode}."
            )
            self._downloader_update_ui('status', {'text': 'Download Falhou!', 'bootstyle': 'danger'})
            self._downloader_update_ui('progress', {'value': 0, 'mode': 'determinate'})

    def check_queue(self):
        # ... (sem alterações) ...
        try:
            while True:
                msg_type, *payload = self.progress_queue.get_nowait()

                if msg_type == "status": self.update_status_textbox(payload[0], tag=payload[1])
                elif msg_type == "progress": 
                    if hasattr(self, 'progress_bar'): self.progress_bar['value'] = payload[0] * 100
                elif msg_type == "batch_progress": 
                    if hasattr(self, 'batch_progress_bar'): self.batch_progress_bar['value'] = payload[0] * 100
                elif msg_type == "finish": self._finalize_processing_ui_state(success=payload[0])
                elif msg_type == "ffmpeg_check": self.update_ffmpeg_status()
                elif msg_type == "update_presenter_preview": self._update_presenter_preview_from_queue(image_path=payload[0])
                elif msg_type == "update_presenter_preview_error": self._update_presenter_preview_from_queue(error_message=payload[0])
                elif msg_type == "messagebox": Messagebox.show_info(payload[2], payload[1], parent=self.root) if payload[0] == 'info' else Messagebox.show_error(payload[2], payload[1], parent=self.root)
                
                elif msg_type == "downloader_log":
                    self.downloader_log_textbox.configure(state="normal")
                    self.downloader_log_textbox.insert("end", f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {payload[0]}\n")
                    self.downloader_log_textbox.see("end")
                    self.downloader_log_textbox.configure(state="disabled")
                elif msg_type == "downloader_ui":
                    widget_name, config = payload
                    if widget_name == 'status': self.downloader_status_label.configure(text=config['text'], bootstyle=config.get('bootstyle', 'default'))
                    elif widget_name == 'progress':
                        if 'mode' in config and config['mode'] == 'indeterminate': 
                            self.downloader_progress_bar.configure(mode='indeterminate')
                            self.downloader_progress_bar.start()
                        else: 
                            self.downloader_progress_bar.stop()
                            self.downloader_progress_bar.configure(mode='determinate')
                            self.downloader_progress_bar['value'] = config['value'] * 100
                    elif widget_name == 'overall_status': self.downloader_overall_status_label.configure(text=config['text'])
                    elif widget_name == 'overall_progress': 
                        self.downloader_overall_progress_bar['value'] = config['value'] * 100
                elif msg_type == "downloader_engine_status":
                    text, style = payload
                    self.downloader_engine_status_label.config(text=text, bootstyle=style)
                elif msg_type == "downloader_init_finished":
                    self._downloader_check_readiness()
                elif msg_type == "downloader_finished":
                    self._downloader_check_readiness()

        except queue.Empty: pass
        finally: self.root.after(100, self.check_queue)
    
    def update_status_textbox(self, text: str, append: bool = True, tag: str = "info"):
        # ... (sem alterações) ...
        self.status_text.configure(state=NORMAL)
        full_log_line = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {text}\n"
        if not append: self.status_text.delete("1.0", END)
        self.status_text.insert(END, full_log_line, tag)
        self.status_text.see(END)
        self.status_text.config(state=DISABLED)
        if tag not in ["debug", "info"]:
            logger.log(logging.INFO if tag != "error" else logging.ERROR, text)

    def save_current_config(self):
        # ... (sem alterações) ...
        if hasattr(self, 'intro_default_text_widget'):
            default_state = self.intro_default_text_widget.cget("state")
            if default_state == 'disabled':
                self.intro_default_text_widget.configure(state=NORMAL)
            intro_default_text = self.intro_default_text_widget.get("1.0", "end").strip()
            if default_state == 'disabled':
                self.intro_default_text_widget.configure(state=DISABLED)
        else:
            intro_default_text = self.intro_default_text_var.get()

        if hasattr(self, 'banner_default_text_widget'):
            banner_state = self.banner_default_text_widget.cget("state")
            if banner_state == 'disabled':
                self.banner_default_text_widget.configure(state=NORMAL)
            banner_default_text = self.banner_default_text_widget.get("1.0", "end").strip()
            if banner_state == 'disabled':
                self.banner_default_text_widget.configure(state=DISABLED)
        else:
            banner_default_text = self.banner_default_text_var.get()

        typing_duration_value = int(self.intro_typing_duration_seconds_var.get() or 10)
        if typing_duration_value not in {10, 15, 20, 30}:
            typing_duration_value = 10
        hold_duration_value = int(self.intro_hold_duration_seconds_var.get() or 2)
        if hold_duration_value <= 0:
            hold_duration_value = 2

        config_to_save = {
            'ffmpeg_path': self.ffmpeg_path_var.get(),
            'output_folder': self.output_folder.get(),
            'last_download_folder': self.download_output_path_var.get(),
            'download_playlist_enabled': self.download_playlist_enabled_var.get(),
            'download_playlist_items': self.download_playlist_items_var.get(),
            'last_image_folder': self.config.get('last_image_folder'),
            'last_root_folder': self.config.get('last_root_folder'),
            'last_mixed_folder': self.config.get('last_mixed_folder'),
            'last_png_folder': self.config.get('last_png_folder'),
            'last_effect_folder': self.config.get('last_effect_folder'),
            'last_presenter_folder': self.config.get('last_presenter_folder'),
            'video_codec': self.video_codec_var.get(),
            'resolution': self.resolution_var.get(),
            'narration_volume': self.narration_volume_var.get(),
            'music_volume': self.music_volume_var.get(),
            'subtitle_fontsize': self.subtitle_fontsize_var.get(),
            'subtitle_textcolor': self.subtitle_textcolor_var.get(),
            'subtitle_outlinecolor': self.subtitle_outlinecolor_var.get(),
            'subtitle_position': self.subtitle_position_var.get(),
            'subtitle_bold': self.subtitle_bold_var.get(),
            'subtitle_italic': self.subtitle_italic_var.get(),
            'subtitle_font_file': self.subtitle_font_file.get(),
            'image_duration': self.image_duration_var.get(),
            'slideshow_transition': self.transition_name_var.get(),
            'slideshow_transition_duration': self.transition_duration_var.get(),
            'slideshow_motion': self.motion_var.get(),
            'png_overlay_path': self.png_overlay_path_var.get(),
            'png_overlay_position': self.png_overlay_position_var.get(),
            'png_overlay_scale': self.png_overlay_scale_var.get(),
            'png_overlay_opacity': self.png_overlay_opacity_var.get(),
            'batch_music_behavior': self.batch_music_behavior_var.get(),
            'add_fade_out': self.add_fade_out_var.get(),
            'fade_out_duration': self.fade_out_duration_var.get(),
            'effect_overlay_path': self.effect_overlay_path_var.get(),
            'effect_blend_mode': self.effect_blend_mode_var.get(),
            'presenter_video_path': self.presenter_video_path_var.get(),
            'presenter_position': self.presenter_position_var.get(),
            'presenter_scale': self.presenter_scale_var.get(),
            'presenter_chroma_enabled': self.presenter_chroma_enabled_var.get(),
            'presenter_chroma_color': self.presenter_chroma_color_var.get(),
            'presenter_chroma_similarity': self.presenter_chroma_similarity_var.get(),
            'presenter_chroma_blend': self.presenter_chroma_blend_var.get(),
            'show_tech_logs': self.show_tech_logs_var.get(),
            'intro_enabled': self.intro_enabled_var.get(),
            'intro_default_text': intro_default_text,
            'intro_language_code': self.intro_language_var.get(),
            'intro_texts': self._collect_intro_texts(),
            'intro_font_choice': self.intro_font_choice_var.get(),
            'intro_font_bold': self.intro_font_bold_var.get(),
            'intro_typing_duration_seconds': typing_duration_value,
            'intro_hold_duration_seconds': hold_duration_value,
            'single_language_code': self.single_language_code_var.get(),
            'banner_enabled': self.banner_enabled_var.get(),
            'banner_default_text': banner_default_text,
            'banner_language_code': self.banner_language_code_var.get(),
            'banner_use_gradient': self.banner_use_gradient_var.get(),
            'banner_solid_color': self.banner_solid_color_var.get(),
            'banner_gradient_start': self.banner_gradient_start_var.get(),
            'banner_gradient_end': self.banner_gradient_end_var.get(),
            'banner_font_color': self.banner_font_color_var.get(),
            'banner_height_ratio': self.banner_height_ratio_var.get(),
            'banner_font_scale': self.banner_font_scale_var.get(),
            'banner_outline_enabled': self.banner_outline_enabled_var.get(),
            'banner_outline_color': self.banner_outline_color_var.get(),
            'banner_outline_offset': self.banner_outline_offset_var.get(),
            'banner_shadow_enabled': self.banner_shadow_enabled_var.get(),
            'banner_shadow_color': self.banner_shadow_color_var.get(),
            'banner_shadow_offset_x': self.banner_shadow_offset_x_var.get(),
            'banner_shadow_offset_y': self.banner_shadow_offset_y_var.get(),
            'banner_duration': self.banner_duration_var.get(),
            'banner_texts': {},
        }
        ConfigManager.save_config(config_to_save)
        logger.info("Configuração guardada.")

    def on_closing(self):
        # ... (sem alterações) ...
        logger.info("Botão de fechar clicado.")
        if self.is_processing or (self.download_thread and self.download_thread.is_alive()):
             if Messagebox.yesno("Um processamento está em andamento. Deseja realmente sair e cancelar a tarefa?", "Sair?", parent=self.root):
                 self.request_cancellation()
             else:
                return

        if self._license_check_job is not None:
            try:
                self.root.after_cancel(self._license_check_job)
            except Exception:
                pass
            self._license_check_job = None

        self.unload_all_font_resources()
        if self.presenter_processed_frame_path and os.path.exists(self.presenter_processed_frame_path):
            try: os.remove(self.presenter_processed_frame_path)
            except OSError as e: logger.warning(f"Não foi possível remover o arquivo temporário {self.presenter_processed_frame_path}: {e}")

        self.save_current_config()
        self.thread_executor.shutdown(wait=False, cancel_futures=True)
        if video_processing_logic and hasattr(video_processing_logic, 'process_manager'):
            video_processing_logic.process_manager.shutdown()
        logger.info("Aplicativo fechado.")
        self.root.destroy()

__all__ = ["VideoEditorApp", "ConfigManager", "SUBTITLE_POSITIONS", "APP_NAME", "CONFIG_FILE"]

if __name__ == "__main__":
    # ... (sem alterações) ...
    root = ttk.Window(themename="superhero")
    app = VideoEditorApp(root, license_data={"data": {"attributes": {"expiry": None}}})
    root.mainloop()