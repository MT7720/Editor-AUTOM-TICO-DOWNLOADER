import math
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


def test_create_typing_intro_clip_respects_custom_durations(tmp_path, monkeypatch):
    captured = {}

    def fake_execute(cmd, duration, progress_callback, cancel_event, log_prefix, progress_queue):
        output_path = Path(cmd[-1])
        output_path.touch()
        return True

    def fake_audio(text, char_duration, hold_duration, output_path, sample_rate=44100):
        captured["char_duration"] = char_duration
        captured["hold_duration"] = hold_duration
        Path(output_path).touch()
        return len(text) * char_duration + hold_duration

    monkeypatch.setattr(typing_renderer, "execute_ffmpeg", fake_execute)
    monkeypatch.setattr(typing_renderer, "generate_typing_audio", fake_audio)

    params = {
        "ffmpeg_path": "ffmpeg",
        "subtitle_style": {},
        "intro_typing_duration_seconds": 2,
        "intro_hold_duration_seconds": 3,
    }
    cancel_event = threading.Event()
    progress_queue: Queue = Queue()

    typing_renderer.create_typing_intro_clip(
        "ABCD",
        (320, 240),
        params,
        str(tmp_path),
        progress_queue,
        cancel_event,
        "Teste",
    )

    assert math.isclose(captured["char_duration"], 2 / 4, rel_tol=1e-3)
    assert math.isclose(captured["hold_duration"], 3, rel_tol=1e-3)


def test_create_typing_intro_clip_invalid_input_uses_defaults(tmp_path, monkeypatch):
    captured = {}

    def fake_execute(cmd, duration, progress_callback, cancel_event, log_prefix, progress_queue):
        output_path = Path(cmd[-1])
        output_path.touch()
        return True

    def fake_audio(text, char_duration, hold_duration, output_path, sample_rate=44100):
        captured["char_duration"] = char_duration
        captured["hold_duration"] = hold_duration
        Path(output_path).touch()
        return len(text) * char_duration + hold_duration

    monkeypatch.setattr(typing_renderer, "execute_ffmpeg", fake_execute)
    monkeypatch.setattr(typing_renderer, "generate_typing_audio", fake_audio)

    params = {
        "ffmpeg_path": "ffmpeg",
        "subtitle_style": {},
        "intro_typing_duration_seconds": 0,
        "intro_hold_duration_seconds": -5,
    }
    cancel_event = threading.Event()
    progress_queue: Queue = Queue()

    typing_renderer.create_typing_intro_clip(
        "",
        (320, 240),
        params,
        str(tmp_path),
        progress_queue,
        cancel_event,
        "Teste",
    )

    default_char_duration = 2 / 30
    assert math.isclose(captured["char_duration"], default_char_duration, rel_tol=1e-3)
    assert math.isclose(captured["hold_duration"], 1.5, rel_tol=1e-3)
