import threading
import wave
from pathlib import Path
from queue import Queue

import pytest
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
        "intro_typing_duration": 100,
        "intro_hold_duration": 800,
        "intro_post_hold_duration": 400,
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

    frames_dir = Path(result["path"]).parent / "frames"
    frame_files = sorted(frames_dir.glob("frame_*.png"))
    assert frame_files

    frame_rate = 30
    expected_frames_per_char = max(1, int(round(frame_rate * (params["intro_typing_duration"] / 1000.0))))
    expected_hold_frames = max(0, int(round(frame_rate * (params["intro_hold_duration"] / 1000.0))))
    expected_post_hold_frames = max(0, int(round(frame_rate * (params["intro_post_hold_duration"] / 1000.0))))
    expected_total_frames = (len("Olá") * expected_frames_per_char) + expected_hold_frames + expected_post_hold_frames

    assert len(frame_files) == expected_total_frames
    assert result["frames_per_char"] == expected_frames_per_char
    assert result["hold_frames"] == expected_hold_frames
    assert result["post_hold_frames"] == expected_post_hold_frames

    expected_duration = expected_total_frames / frame_rate
    assert result["duration"] == pytest.approx(expected_duration, rel=1e-6)
    assert result["typing_duration"] == pytest.approx(len("Olá") * expected_frames_per_char / frame_rate, rel=1e-6)
    assert result["hold_duration"] == pytest.approx(expected_hold_frames / frame_rate, rel=1e-6)
    assert result["post_hold_duration"] == pytest.approx(expected_post_hold_frames / frame_rate, rel=1e-6)

    audio_path = Path(result["path"]).parent / "typing_audio.wav"
    assert audio_path.is_file()
    with audio_path.open("rb") as raw_audio:
        with wave.open(raw_audio) as audio_file:
            total_samples = audio_file.getnframes()
            sample_rate = audio_file.getframerate()

    expected_audio_duration = (
        len("Olá") * (expected_frames_per_char / frame_rate)
        + expected_hold_frames / frame_rate
        + expected_post_hold_frames / frame_rate
    )
    assert total_samples / sample_rate == pytest.approx(expected_audio_duration, rel=1e-3)
