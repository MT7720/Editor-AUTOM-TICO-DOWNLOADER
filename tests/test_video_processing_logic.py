import json
import subprocess

import video_processing_logic as v


def test_parse_resolution():
    assert v._parse_resolution("720p (1280x720)") == (1280, 720)
    assert v._parse_resolution("invalid") == (1920, 1080)


def test_get_codec_params_copy():
    params = {"video_codec": "Automático", "available_encoders": []}
    assert v._get_codec_params(params, False) == ["-c:v", "copy"]


def test_get_codec_params_gpu():
    params = {"video_codec": "Automático", "available_encoders": ["h264_nvenc"]}
    out = v._get_codec_params(params, True)
    assert out[1] == "h264_nvenc"


def test_build_subtitle_style_string():
    style = {
        "fontsize": 24,
        "text_color": "#FF0000",
        "outline_color": "#00FF00",
        "bold": True,
        "italic": False,
        "position": "Center",
        "font_file": "test.ttf",
        "position_map": {"Center": 2},
    }
    result = v._build_subtitle_style_string(style)
    assert "FontName=test" in result
    assert "FontSize=24" in result
    assert "PrimaryColour=&H0000FF" in result
    assert "OutlineColour=&H00FF00" in result
    assert "Alignment=2" in result


def test_probe_media_properties(tmp_path, monkeypatch):
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("")
    ffprobe = tmp_path / "ffprobe"
    ffprobe.write_text("")
    media = tmp_path / "input.mp4"
    media.write_text("dummy")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"streams": []}))

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = v._probe_media_properties(str(media), str(ffmpeg))
    assert result == {"streams": []}


def test_probe_media_properties_no_ffprobe(tmp_path):
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("")
    media = tmp_path / "input.mp4"
    media.write_text("dummy")

    assert v._probe_media_properties(str(media), str(ffmpeg)) is None
