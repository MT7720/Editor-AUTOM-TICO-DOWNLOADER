import base64
import importlib
import json
import os
import sys

import pytest

from security import secrets
from gui import constants as gui_constants
import gui.config_manager as config_manager


@pytest.fixture(autouse=True)
def reset_secret_caches():
    if hasattr(secrets._load_config_data, "cache_clear"):
        secrets._load_config_data.cache_clear()
    yield
    if hasattr(secrets._load_config_data, "cache_clear"):
        secrets._load_config_data.cache_clear()


def _reload_license_checker():
    sys.modules.pop("license_checker", None)
    module = importlib.import_module("license_checker")
    module.get_license_service_credentials.cache_clear()
    return module


def _clear_license_env(monkeypatch):
    for env_var in (
        "LICENSE_SERVICE_BUNDLE",
        "LICENSE_SERVICE_BUNDLE_PATH",
        "LICENSE_API_URL",
        "LICENSE_API_TOKEN",
    ):
        monkeypatch.delenv(env_var, raising=False)


def test_load_license_secrets_from_env(monkeypatch):
    _clear_license_env(monkeypatch)
    monkeypatch.setenv("LICENSE_API_URL", "https://example.test/api/")
    monkeypatch.setenv("LICENSE_API_TOKEN", "env-token")

    credentials = secrets.load_license_secrets()

    assert credentials.api_token == "env-token"
    assert credentials.api_base_url == "https://example.test/api"


def test_load_license_secrets_from_bundle(monkeypatch):
    _clear_license_env(monkeypatch)
    payload = {
        "api_token": "bundle-token",
        "api_base_url": "https://bundle.test/api",
        "proof": "signed",
    }
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    monkeypatch.setenv("LICENSE_SERVICE_BUNDLE", encoded)

    credentials = secrets.load_license_secrets()

    assert credentials.api_token == "bundle-token"
    assert credentials.api_base_url == "https://bundle.test/api"


def test_load_license_secrets_from_local_installation(monkeypatch, tmp_path):
    payload = {
        "api_token": "local-token",
        "api_base_url": "https://local.test/api",
        "proof": "embedded",
    }

    bundle_path = tmp_path / "credentials.json"
    bundle_path.write_text(json.dumps(payload), encoding="utf-8")
    if os.name != "nt":
        bundle_path.chmod(0o600)

    config_path = tmp_path / "video_editor_config.json"

    _clear_license_env(monkeypatch)
    monkeypatch.setattr(
        secrets,
        "_iter_local_bundle_candidates",
        lambda: (bundle_path,),
    )
    monkeypatch.setattr(
        secrets,
        "_load_config_data",
        lambda: (config_path, {}),
    )

    credentials = secrets.load_license_secrets()

    assert credentials.api_token == "local-token"
    assert credentials.api_base_url == "https://local.test/api"


def test_load_license_secrets_from_inline_config(monkeypatch, tmp_path):
    config_data = {
        "license_api_token": "inline-token",
        "license_api_url": "https://inline.test/api",
    }

    _clear_license_env(monkeypatch)

    def fake_load_config_data():
        return tmp_path / "video_editor_config.json", config_data

    monkeypatch.setattr(secrets, "_load_config_data", fake_load_config_data)

    credentials = secrets.load_license_secrets()

    assert credentials.api_token == "inline-token"
    assert credentials.api_base_url == "https://inline.test/api"


def test_inline_credentials_survive_config_roundtrip(monkeypatch, tmp_path):
    config_path = tmp_path / "video_editor_config.json"
    initial_config = {
        "license_api_token": "roundtrip-token",
        "license_api_url": "https://roundtrip.test/api",
        "license_credentials_path": "relative/path/to/credentials.json",
        "ffmpeg_path": "",
    }
    config_path.write_text(json.dumps(initial_config), encoding="utf-8")

    monkeypatch.setattr(gui_constants, "CONFIG_FILE", str(config_path))
    monkeypatch.setattr(config_manager, "CONFIG_FILE", str(config_path))
    monkeypatch.setattr(secrets, "_iter_config_candidates", lambda: (config_path,))

    _clear_license_env(monkeypatch)

    loaded_config = config_manager.ConfigManager.load_config()

    assert loaded_config["license_api_token"] == "roundtrip-token"
    assert loaded_config["license_api_url"] == "https://roundtrip.test/api"
    assert loaded_config["license_credentials_path"] == "relative/path/to/credentials.json"

    config_without_secrets = {
        key: value
        for key, value in loaded_config.items()
        if not key.startswith("license_")
    }
    config_without_secrets["output_folder"] = "some/other/path"

    config_manager.ConfigManager.save_config(config_without_secrets)

    reloaded_config = config_manager.ConfigManager.load_config()
    assert reloaded_config["license_api_token"] == "roundtrip-token"
    assert reloaded_config["license_api_url"] == "https://roundtrip.test/api"
    assert reloaded_config["license_credentials_path"] == "relative/path/to/credentials.json"

    credentials = secrets.load_license_secrets()
    assert credentials.api_token == "roundtrip-token"
    assert credentials.api_base_url == "https://roundtrip.test/api"


def test_load_license_secrets_with_minor_json_error(monkeypatch, tmp_path):
    raw_config = """{
  \"license_api_token\": \"inline-token\"
  \"license_api_url\": \"https://inline.test/api\"
}"""

    config_path = tmp_path / "video_editor_config.json"
    config_path.write_text(raw_config, encoding="utf-8")

    _clear_license_env(monkeypatch)

    monkeypatch.setattr(
        secrets,
        "_iter_config_candidates",
        lambda: (config_path,),
    )

    credentials = secrets.load_license_secrets()

    assert credentials.api_token == "inline-token"
    assert credentials.api_base_url == "https://inline.test/api"


def test_missing_configuration_raises_error(monkeypatch):
    _clear_license_env(monkeypatch)
    monkeypatch.setattr(secrets, "_load_bundle_from_local_installation", lambda: None)

    with pytest.raises(secrets.SecretLoaderError) as excinfo:
        secrets.load_license_secrets()

    message = str(excinfo.value)
    lowered = message.lower()
    assert "credenciais" in lowered
    assert "license_service_bundle" in lowered


def test_license_checker_exposes_cached_credentials(monkeypatch):
    _clear_license_env(monkeypatch)
    monkeypatch.setenv("LICENSE_API_URL", "https://cached.test/api")
    monkeypatch.setenv("LICENSE_API_TOKEN", "cached-token")

    module = _reload_license_checker()

    credentials = module.get_license_service_credentials()
    assert credentials.api_token == "cached-token"
    assert module.get_product_token() == "cached-token"
    assert module.get_api_base_url() == "https://cached.test/api"

    monkeypatch.setenv("LICENSE_API_TOKEN", "updated-token")
    assert module.get_product_token() == "cached-token"

    module.get_license_service_credentials.cache_clear()
    assert module.get_product_token() == "updated-token"


def test_empty_environment_raises_error(monkeypatch):
    monkeypatch.setenv("LICENSE_SERVICE_BUNDLE", "")
    monkeypatch.setenv("LICENSE_SERVICE_BUNDLE_PATH", "")
    monkeypatch.setenv("LICENSE_API_URL", "")
    monkeypatch.setenv("LICENSE_API_TOKEN", "")

    monkeypatch.setattr(secrets, "_load_bundle_from_local_installation", lambda: None)

    with pytest.raises(secrets.SecretLoaderError):
        secrets.load_license_secrets()


def test_validate_license_with_missing_credentials(monkeypatch):
    _clear_license_env(monkeypatch)

    module = _reload_license_checker()
    module.get_license_service_credentials.cache_clear()

    def _raise_secret_loader_error():
        raise secrets.SecretLoaderError("Credenciais indisponíveis")

    monkeypatch.setattr(module, "load_license_secrets", _raise_secret_loader_error)
    module.get_license_service_credentials.cache_clear()

    payload, error, invalid_detail = module.validate_license_key("any", "fingerprint")

    assert payload is None
    assert "credenciais" in error.lower()
    assert invalid_detail is None


def test_activate_new_license_with_missing_credentials(monkeypatch):
    _clear_license_env(monkeypatch)

    module = _reload_license_checker()
    module.get_license_service_credentials.cache_clear()

    def _raise_secret_loader_error():
        raise secrets.SecretLoaderError("Credenciais indisponíveis")

    monkeypatch.setattr(module, "load_license_secrets", _raise_secret_loader_error)
    module.get_license_service_credentials.cache_clear()

    activation_data, message, error_code = module.activate_new_license("token", "fingerprint")

    assert activation_data is None
    message_lower = message.lower()
    assert (
        "credenciais" in message_lower
        or module.MIGRATION_REQUIRED_MESSAGE.lower() in message_lower
    )
    assert error_code is None or error_code == "migration_required"
