import importlib.util
import os
import platform
import shutil
import sys
import subprocess
import types

import pytest


def load_ffmpeg_manager():
    package_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "gui"))

    if "gui" not in sys.modules:
        gui_package = types.ModuleType("gui")
        gui_package.__path__ = [package_path]
        sys.modules["gui"] = gui_package

    utils_path = os.path.join(package_path, "utils.py")
    if "gui.utils" not in sys.modules:
        utils_spec = importlib.util.spec_from_file_location("gui.utils", utils_path)
        utils_module = importlib.util.module_from_spec(utils_spec)
        assert utils_spec and utils_spec.loader  # defensive
        sys.modules["gui.utils"] = utils_module
        utils_spec.loader.exec_module(utils_module)

    module_path = os.path.join(package_path, "ffmpeg_manager.py")
    spec = importlib.util.spec_from_file_location("gui.ffmpeg_manager", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader  # defensive
    sys.modules["gui.ffmpeg_manager"] = module
    spec.loader.exec_module(module)
    return module.FFmpegManager


FFmpegManager = load_ffmpeg_manager()


@pytest.mark.parametrize(
    "target_path,env_overrides",
    [
        ("C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe", {"ProgramFiles": "C:\\Program Files"}),
        ("C:\\Program Files (x86)\\ffmpeg\\bin\\ffmpeg.exe", {"ProgramFiles(x86)": "C:\\Program Files (x86)"}),
    ],
)
def test_find_executable_windows_architectures(monkeypatch, caplog, target_path, env_overrides):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(shutil, "which", lambda _: None)

    for key in ["ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"]:
        monkeypatch.delenv(key, raising=False)
    for key, value in env_overrides.items():
        monkeypatch.setenv(key, value)

    checked_paths = []

    def fake_exists(path: str) -> bool:
        normalized = path.replace("/", "\\")
        checked_paths.append(normalized)
        return normalized == target_path

    monkeypatch.setattr(os.path, "exists", fake_exists)
    monkeypatch.setattr(sys, "executable", "C:\\Python\\python.exe")
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    with caplog.at_level("INFO"):
        result = FFmpegManager.find_executable()

    assert result is not None
    assert result.replace("/", "\\") == target_path
    assert target_path in checked_paths
    assert any(target_path in message.replace("/", "\\") for message in caplog.messages)


def test_find_executable_checks_application_directories(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(shutil, "which", lambda _: None)

    for key in ["ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"]:
        monkeypatch.delenv(key, raising=False)

    app_dir = tmp_path / "app"
    ffmpeg_dir = app_dir / "ffmpeg" / "bin"
    ffmpeg_dir.mkdir(parents=True)
    ffmpeg_path = str(ffmpeg_dir / "ffmpeg.exe").replace("/", "\\")

    checked_paths = []

    def fake_exists(path: str) -> bool:
        normalized = path.replace("/", "\\")
        checked_paths.append(normalized)
        return normalized == ffmpeg_path

    monkeypatch.setattr(os.path, "exists", fake_exists)
    monkeypatch.setattr(sys, "_MEIPASS", str(app_dir), raising=False)
    monkeypatch.setattr(sys, "executable", str(app_dir / "app.exe"))

    with caplog.at_level("INFO"):
        result = FFmpegManager.find_executable()

    assert result is not None
    assert result.replace("/", "\\") == ffmpeg_path
    assert ffmpeg_path in checked_paths
    assert any(ffmpeg_path in message.replace("/", "\\") for message in caplog.messages)


def test_check_encoders_detects_multiple_backends(monkeypatch):
    monkeypatch.setattr(os.path, "isfile", lambda _: True)

    def fake_run(*args, **kwargs):
        class Result:
            stdout = """
            V..... h264_nvenc           NVIDIA NVENC H.264 encoder (codec h264)
            V..... hevc_qsv            Intel Quick Sync HEVC encoder (codec hevc)
            V..... h264_amf            AMD AMF H.264 encoder (codec h264)
            V..... hevc_vaapi          VAAPI HEVC encoder (codec hevc)
        """

        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)

    encoders = FFmpegManager.check_encoders("/tmp/ffmpeg")

    assert {"libx264", "h264_nvenc", "hevc_qsv", "h264_amf", "hevc_vaapi"}.issubset(encoders)
