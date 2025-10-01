import threading
from queue import Empty, Queue

import pytest

from video_processing import final_pass


def _drain_queue(q: Queue) -> list:
    items = []
    while True:
        try:
            items.append(q.get_nowait())
        except Empty:
            break
    return items


def test_fade_out_starts_after_narration(tmp_path, monkeypatch):
    base_video = tmp_path / "base.mp4"
    base_video.write_bytes(b"0")
    narration = tmp_path / "voice.mp3"
    narration.write_bytes(b"0")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    params = {
        'ffmpeg_path': 'ffmpeg',
        'resolution': '1920x1080',
        'subtitle_style': {},
        'output_folder': str(output_dir),
        'output_filename_single': 'final.mp4',
        'add_fade_out': True,
        'fade_out_duration': 4.0,
        'narration_volume': 0,
        'music_volume': 0,
        'video_codec': 'Automático',
        'available_encoders': [],
    }

    captured = {}

    def fake_execute(cmd, total_duration, progress_cb, cancel_event, log_prefix, progress_queue):
        captured['cmd'] = cmd
        captured['total_duration'] = total_duration
        return True

    monkeypatch.setattr(final_pass, "_execute_ffmpeg", fake_execute)
    monkeypatch.setattr(final_pass, "_maybe_create_intro_clip", lambda *args, **kwargs: None)
    monkeypatch.setattr(final_pass, "_combine_intro_with_main", lambda *args, **kwargs: True)
    monkeypatch.setattr(final_pass, "_create_styled_ass_from_srt", lambda *args, **kwargs: None)
    monkeypatch.setattr(final_pass, "_get_codec_params", lambda *args, **kwargs: ['-c:v', 'copy'])

    durations = {
        str(base_video): {'format': {'duration': '20.0'}},
        str(narration): {'format': {'duration': '12.5'}},
    }

    monkeypatch.setattr(final_pass, "_probe_media_properties", lambda path, ffmpeg: durations.get(path))

    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()

    progress_queue: Queue = Queue()
    cancel_event = threading.Event()

    result = final_pass._perform_final_pass(
        params=params,
        base_video_path=str(base_video),
        narration_path=str(narration),
        music_paths=[],
        subtitle_path=None,
        progress_queue=progress_queue,
        cancel_event=cancel_event,
        temp_dir=str(temp_dir),
        log_prefix="teste",
    )

    assert result is True
    # Duração final deve considerar o conteúdo mais longo e o tempo extra do fade-out.
    expected_total = max(20.0, 12.5 + 4.0)
    assert captured['total_duration'] == pytest.approx(expected_total)

    cmd = captured['cmd']
    assert '-t' in cmd
    total_arg = float(cmd[cmd.index('-t') + 1])
    assert total_arg == pytest.approx(expected_total)

    filter_str = cmd[cmd.index('-filter_complex') + 1]
    assert "fade=t=out:st=12.5" in filter_str
    assert "afade=t=out:st=12.5" in filter_str

    logs = _drain_queue(progress_queue)
    fade_logs = [entry for entry in logs if entry[0] == "status" and "Fade-out configurado" in entry[1]]
    assert fade_logs, "Expected fade-out status log to be emitted"

