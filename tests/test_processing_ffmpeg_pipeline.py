import threading
from queue import Queue

import os

from processing import ffmpeg_pipeline


def test_escape_ffmpeg_path_formats_windows_style():
    escaped = ffmpeg_pipeline.escape_ffmpeg_path("C:\\Videos\\clip.mp4")
    assert escaped == "C\\:/Videos/clip.mp4"


def test_execute_ffmpeg_reports_missing_binary(monkeypatch):
    queue: Queue = Queue()
    cancel_event = threading.Event()

    monkeypatch.setattr(os.path, "isfile", lambda _: False)

    result = ffmpeg_pipeline.execute_ffmpeg(["/path/to/ffmpeg"], 1.0, None, cancel_event, "Teste", queue)
    assert result is False
    status, message, level = queue.get_nowait()
    assert level == "error"
    assert "FFmpeg" in message


def test_get_codec_params_prefers_copy_without_reencode():
    params = {"video_codec": "Automático", "available_encoders": []}
    result = ffmpeg_pipeline.get_codec_params(params, force_reencode=False)
    assert result == ["-c:v", "copy"]
