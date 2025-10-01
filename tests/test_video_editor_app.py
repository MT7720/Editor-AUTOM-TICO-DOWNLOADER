import pytest
from pyvirtualdisplay import Display
from main import VideoEditorApp, SUBTITLE_POSITIONS


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
