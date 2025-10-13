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

    params = {
        "ffmpeg_path": "ffmpeg",
        "subtitle_style": {},
        "intro_font_choice": "Arial",
        "intro_font_bold": True,
    }
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
    created_outputs = []
    captured = {}

    def fake_execute(cmd, duration, progress_callback, cancel_event, log_prefix, progress_queue):
        output_path = Path(cmd[-1])
        output_path.touch()
        created_outputs.append(output_path)
        return True

    def fake_generate(text, char_duration, hold_duration, output_path, sample_rate=44100):
        captured["char_duration"] = char_duration
        captured["hold_duration"] = hold_duration
        Path(output_path).touch()
        return len(text) * char_duration

    monkeypatch.setattr(typing_renderer, "execute_ffmpeg", fake_execute)
    monkeypatch.setattr(typing_renderer, "generate_typing_audio", fake_generate)

    params = {
        "ffmpeg_path": "ffmpeg",
        "subtitle_style": {},
        "intro_font_choice": "Arial",
        "intro_font_bold": False,
        "intro_typing_duration_seconds": 20,
        "intro_hold_duration_seconds": 6,
    }
    cancel_event = threading.Event()
    progress_queue: Queue = Queue()

    result = typing_renderer.create_typing_intro_clip(
        "Config",
        (320, 240),
        params,
        str(tmp_path),
        progress_queue,
        cancel_event,
        "Teste",
    )

    assert result is not None
    assert Path(result["path"]).exists()
    assert created_outputs
    assert math.isclose(captured["hold_duration"], 6.0, rel_tol=1e-6)
    expected_char_base = params["intro_typing_duration_seconds"] / typing_renderer.REFERENCE_CHAR_COUNT
    expected_frames = max(2, int(round(30 * expected_char_base)))
    expected_char_duration = expected_frames / 30.0
    assert math.isclose(captured["char_duration"], expected_char_duration, rel_tol=0.05)


def test_create_typing_intro_clip_invalid_durations_fallback(tmp_path, monkeypatch):
    created_outputs = []
    captured = {}

    def fake_execute(cmd, duration, progress_callback, cancel_event, log_prefix, progress_queue):
        output_path = Path(cmd[-1])
        output_path.touch()
        created_outputs.append(output_path)
        return True

    def fake_generate(text, char_duration, hold_duration, output_path, sample_rate=44100):
        captured["char_duration"] = char_duration
        captured["hold_duration"] = hold_duration
        Path(output_path).touch()
        return len(text) * char_duration

    monkeypatch.setattr(typing_renderer, "execute_ffmpeg", fake_execute)
    monkeypatch.setattr(typing_renderer, "generate_typing_audio", fake_generate)

    params = {
        "ffmpeg_path": "ffmpeg",
        "subtitle_style": {},
        "intro_font_choice": "Arial",
        "intro_font_bold": False,
        "intro_typing_duration_seconds": -5,
        "intro_hold_duration_seconds": 0,
    }
    cancel_event = threading.Event()
    progress_queue: Queue = Queue()

    result = typing_renderer.create_typing_intro_clip(
        "",
        (320, 240),
        params,
        str(tmp_path),
        progress_queue,
        cancel_event,
        "Teste",
    )

    assert result is not None
    assert Path(result["path"]).exists()
    assert created_outputs

    expected_char_base = typing_renderer.DEFAULT_TYPING_DURATION_SECONDS / typing_renderer.REFERENCE_CHAR_COUNT
    expected_frames = max(2, int(round(30 * expected_char_base)))
    expected_char_duration = expected_frames / 30.0
    assert math.isclose(captured["char_duration"], expected_char_duration, rel_tol=1e-6)

    expected_hold_frames = max(30, int(round(30 * typing_renderer.DEFAULT_HOLD_DURATION_SECONDS)))
    expected_hold_duration = expected_hold_frames / 30.0
    assert math.isclose(captured["hold_duration"], expected_hold_duration, rel_tol=1e-6)
