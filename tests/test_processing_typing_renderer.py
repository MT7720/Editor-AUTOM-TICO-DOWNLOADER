import threading
from pathlib import Path
from queue import Queue

from PIL import ImageFont

from processing import typing_renderer


def test_wrap_text_to_width_breaks_long_words():
    font = ImageFont.load_default()
    lines = typing_renderer.wrap_text_to_width("palavra muito grande", font, 30)
    assert lines
    assert any(len(line) < len("palavra muito grande") for line in lines)


def test_create_typing_intro_clip_smoke(tmp_path, monkeypatch):
    created_outputs = []

    def fake_execute(cmd, duration, progress_callback, cancel_event, log_prefix, progress_queue):
        output_path = Path(cmd[-1])
        output_path.touch()
        created_outputs.append(output_path)
        return True

    monkeypatch.setattr(typing_renderer, "execute_ffmpeg", fake_execute)

    params = {"ffmpeg_path": "ffmpeg", "subtitle_style": {}}
    cancel_event = threading.Event()
    progress_queue: Queue = Queue()

    result = typing_renderer.create_typing_intro_clip(
        "Olá",
        (320, 240),
        params,
        str(tmp_path),
        progress_queue,
        cancel_event,
        "Teste",
    )

    assert result is not None
    assert Path(result["path"]).exists()
    assert created_outputs  # garante que o executável fake foi chamado
