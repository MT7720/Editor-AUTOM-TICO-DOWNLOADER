import io
import pytest
import gui.app as app_module
from pyvirtualdisplay import Display
from gui.app import VideoEditorApp
from gui.constants import SUBTITLE_POSITIONS


@pytest.fixture(scope="module")
def app():
    try:
        display = Display(visible=0, size=(800, 600))
        display.start()
    except FileNotFoundError:
        pytest.skip("Xvfb não está disponível no ambiente de testes.")

    application = VideoEditorApp()
    try:
        yield application
    finally:
        application.root.destroy()
        display.stop()


def test_gather_processing_params(app):
    app.ffmpeg_path_var.set("/usr/bin/ffmpeg")
    app.subtitle_fontsize_var.set(32)
    app.subtitle_textcolor_var.set("#ABCDEF")
    app.subtitle_outlinecolor_var.set("#123456")
    app.subtitle_bold_var.set(False)
    app.subtitle_italic_var.set(True)
    app.subtitle_position_var.set(list(SUBTITLE_POSITIONS.keys())[0])
    app.subtitle_font_file.set("/tmp/font.ttf")
    app.available_encoders_cache = ["libx264"]

    params = app._gather_processing_params()
    assert params["ffmpeg_path"] == "/usr/bin/ffmpeg"
    assert params["available_encoders"] == ["libx264"]
    style = params["subtitle_style"]
    assert style["fontsize"] == 32
    assert style["text_color"] == "#ABCDEF"
    assert style["outline_color"] == "#123456"
    assert style["bold"] is False
    assert style["italic"] is True
    assert style["font_file"] == "/tmp/font.ttf"


def _visible(widget):
    widget.update_idletasks()
    return widget.winfo_manager() != ""


def test_update_ui_for_media_type(app):
    app.media_type.set("video_single")
    app.update_ui_for_media_type()
    app.root.update()
    assert _visible(app.single_inputs_frame)
    assert not _visible(app.batch_inputs_frame)
    assert not _visible(app.slideshow_section)

    app.media_type.set("image_folder")
    app.update_ui_for_media_type()
    app.root.update()
    assert _visible(app.slideshow_section)
    assert _visible(app.single_inputs_frame)
    assert not _visible(app.batch_inputs_frame)

    app.media_type.set("batch")
    app.update_ui_for_media_type()
    app.root.update()
    assert not _visible(app.single_inputs_frame)
    assert _visible(app.batch_inputs_frame)
    assert not _visible(app.slideshow_section)

    app.media_type.set("batch_image_hierarchical")
    app.update_ui_for_media_type()
    app.root.update()
    assert _visible(app.batch_inputs_frame)
    assert _visible(app.batch_hierarchical_inputs_frame)
    assert _visible(app.video_settings_section)
    assert not _visible(app.slideshow_section)


def test_check_available_encoders_updates_ui(app, monkeypatch):
    simulated_encoders = [
        "libx264",
        "h264_nvenc",
        "hevc_qsv",
        "h264_amf",
    ]
    monkeypatch.setattr(app_module.FFmpegManager, "check_encoders", lambda _: simulated_encoders)

    app.ffmpeg_path_var.set("/tmp/ffmpeg")
    app._check_available_encoders()

    values = tuple(app.video_codec_combobox.cget("values"))
    assert "GPU (NVIDIA NVENC H.264)" in values
    assert "GPU (Intel QSV HEVC)" in values
    assert "GPU (AMD AMF H.264)" in values

    status_text = app.gpu_status_label.cget("text")
    assert "NVIDIA NVENC" in status_text
    assert "Intel Quick Sync Video" in status_text
    assert "AMD AMF" in status_text


def test_downloader_playlist_flag_modifies_command(app, monkeypatch):
    captured_commands = []

    class DummyProcess:
        def __init__(self, cmd, *args, **kwargs):
            captured_commands.append(cmd)
            self.stdout = io.StringIO(
                '{"type":"download","status":"finished","percent":"100%","eta":"00:00","index":"1","count":"1"}\n'
            )
            self.returncode = 0

        def wait(self):
            return self.returncode

    monkeypatch.setattr(app_module.subprocess, "Popen", DummyProcess)

    app.yt_dlp_engine_path = "yt-dlp"
    app.ffmpeg_path_var.set("/usr/bin/ffmpeg")
    app.download_output_path_var.set("/tmp")

    app._downloader_overall_total = 1
    app._downloader_overall_completed = 0
    app.download_playlist_enabled_var.set(False)
    app.download_playlist_items_var.set("")
    app._downloader_download_single_video("https://example.com/watch?v=123")

    assert captured_commands, "Nenhum comando foi capturado."
    command_no_playlist = captured_commands[-1]
    assert "--no-playlist" in command_no_playlist
    assert "--yes-playlist" not in command_no_playlist

    app._downloader_overall_total = 3
    app._downloader_overall_completed = 0
    app.download_playlist_enabled_var.set(True)
    app.download_playlist_items_var.set("1-3")
    app._downloader_download_single_video("https://example.com/playlist", expected_entries=3)

    command_with_playlist = captured_commands[-1]
    assert "--no-playlist" not in command_with_playlist
    assert "--yes-playlist" in command_with_playlist
    assert "--playlist-items" in command_with_playlist
    assert any(arg == "1-3" for arg in command_with_playlist)
