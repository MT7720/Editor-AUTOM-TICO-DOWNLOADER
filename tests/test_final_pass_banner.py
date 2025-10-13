import threading
from pathlib import Path
from queue import Queue

from PIL import Image

from video_processing import final_pass
from video_processing.banner import compute_banner_height


def test_banner_overlay_creates_gradient_and_filter(tmp_path, monkeypatch):
    base_video = tmp_path / "base.mp4"
    base_video.write_bytes(b"00")

    params = {
        'ffmpeg_path': 'ffmpeg',
        'resolution': '1280x720',
        'subtitle_style': {'font_file': ''},
        'output_folder': str(tmp_path),
        'output_filename_single': 'output.mp4',
        'add_fade_out': False,
        'narration_volume': 0,
        'music_volume': 0,
        'video_codec': 'Automático',
        'available_encoders': [],
        'banner_enabled': True,
        'banner_default_text': 'Olá mundo',
        'banner_texts': {'ES': 'Hola mundo'},
        'banner_language_code': 'auto',
        'banner_use_gradient': True,
        'banner_solid_color': '#123456',
        'banner_gradient_start': '#112233',
        'banner_gradient_end': '#445566',
        'banner_font_color': '#FFFFFF',
        'banner_duration': 3.5,
        'current_language_code': 'es',
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
        str(base_video): {'format': {'duration': '12.0'}},
    }

    monkeypatch.setattr(final_pass, "_probe_media_properties", lambda path, ffmpeg: durations.get(path))

    temp_dir = tmp_path / "tmp"
    temp_dir.mkdir()

    progress_queue: Queue = Queue()

    assert final_pass._perform_final_pass(
        params=params,
        base_video_path=str(base_video),
        narration_path=None,
        music_paths=[],
        subtitle_path=None,
        progress_queue=progress_queue,
        cancel_event=threading.Event(),
        temp_dir=str(temp_dir),
        log_prefix="teste",
    )

    overlay_path = Path(params['banner_overlay_path'])
    assert overlay_path.exists()
    assert params['banner_final_text'] == 'Hola mundo'

    with Image.open(overlay_path) as img:
        expected_height = compute_banner_height(720)
        assert img.size == (1280, expected_height)
        top_pixel = img.getpixel((img.width // 2, 0))[:3]
        bottom_pixel = img.getpixel((img.width // 2, img.height - 1))[:3]
        assert top_pixel != bottom_pixel
        assert top_pixel == (0x11, 0x22, 0x33)
        assert bottom_pixel == (0x44, 0x55, 0x66)

    cmd = captured['cmd']
    assert '-filter_complex' in cmd
    filter_str = cmd[cmd.index('-filter_complex') + 1]
    assert "overlay=0:0:enable='between(t,0,3.500)'" in filter_str
    assert '-loop' in cmd
    assert params['banner_overlay_duration'] == 3.5
