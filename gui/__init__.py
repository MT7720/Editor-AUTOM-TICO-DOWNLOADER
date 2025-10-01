"""High level exports for the GUI package."""

from __future__ import annotations

import ttkbootstrap as ttk

from .app import VideoEditorApp
from .config_manager import ConfigManager
from .constants import *  # noqa: F401,F403 - re-export for compatibility
from .ffmpeg_manager import FFmpegManager
from .previews import PngPreview, PresenterPreview, SubtitlePreview
from .utils import logger

__all__ = [
    "ConfigManager",
    "FFmpegManager",
    "SubtitlePreview",
    "PngPreview",
    "PresenterPreview",
    "VideoEditorApp",
    "logger",
    "run_app",
]
__all__ += [name for name in globals().keys() if name.isupper()]


def run_app(*, license_data=None, root=None, themename: str = "superhero") -> VideoEditorApp:
    """Convenience entry point to build and launch the GUI."""
    if root is None:
        root = ttk.Window(themename=themename)
    app = VideoEditorApp(root=root, license_data=license_data)
    if not root.winfo_viewable():
        root.deiconify()
    root.mainloop()
    return app
