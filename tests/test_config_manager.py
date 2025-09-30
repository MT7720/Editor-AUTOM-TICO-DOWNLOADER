import json
import os
from main import ConfigManager, CONFIG_FILE


def test_save_and_load_config(tmp_path, monkeypatch):
    temp_file = tmp_path / "config.json"
    monkeypatch.setattr("main.CONFIG_FILE", str(temp_file))

    sample = {"ffmpeg_path": "path/to/ffmpeg", "music_volume": -20}
    ConfigManager.save_config(sample)

    assert temp_file.exists()
    with open(temp_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data == sample

    loaded = ConfigManager.load_config()
    for key, value in sample.items():
        assert loaded[key] == value
