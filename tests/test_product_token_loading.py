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


def test_load_license_secrets_from_env(monkeypatch):
    monkeypatch.setenv("KEYGEN_ACCOUNT_ID", "env-account")
    monkeypatch.setenv("KEYGEN_PRODUCT_TOKEN", "env-token")
    monkeypatch.setenv("KEYGEN_API_BASE_URL", "https://example.test/accounts/env-account")
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE", raising=False)
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE_PATH", raising=False)

    credentials = secrets.load_license_secrets()

    assert credentials.account_id == "env-account"
    assert credentials.product_token == "env-token"
    assert credentials.api_base_url == "https://example.test/accounts/env-account"


def test_load_license_secrets_from_bundle(monkeypatch):
    payload = {
        "account_id": "bundle-account",
        "product_token": "bundle-token",
        "channel": "brokered",
    }
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")

    monkeypatch.setenv("KEYGEN_LICENSE_BUNDLE", encoded)
    monkeypatch.delenv("KEYGEN_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("KEYGEN_PRODUCT_TOKEN", raising=False)

    credentials = secrets.load_license_secrets()

    assert credentials.account_id == "bundle-account"
    assert credentials.product_token == "bundle-token"
    assert credentials.api_base_url.endswith("/bundle-account")


def test_load_license_secrets_from_local_installation(monkeypatch, tmp_path):
    payload = {
        "account_id": "local-account",
        "product_token": "local-token",
        "channel": "brokered",
    }

    bundle_path = tmp_path / "credentials.json"
    bundle_path.write_text(json.dumps(payload), encoding="utf-8")
    if os.name != "nt":
        bundle_path.chmod(0o600)

    config_path = tmp_path / "video_editor_config.json"

    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE", raising=False)
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE_PATH", raising=False)
    monkeypatch.delenv("KEYGEN_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("KEYGEN_PRODUCT_TOKEN", raising=False)
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

    assert credentials.account_id == "local-account"
    assert credentials.product_token == "local-token"
    assert credentials.api_base_url.endswith("/local-account")


def test_load_license_secrets_from_inline_config(monkeypatch, tmp_path):
    config_data = {
        "license_account_id": "inline-account",
        "license_product_token": "inline-token",
        "license_api_base_url": "https://example.test/accounts/inline-account",
    }

    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE", raising=False)
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE_PATH", raising=False)
    monkeypatch.delenv("KEYGEN_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("KEYGEN_PRODUCT_TOKEN", raising=False)

    def fake_load_config_data():
        return tmp_path / "video_editor_config.json", config_data

    monkeypatch.setattr(secrets, "_load_config_data", fake_load_config_data)

    credentials = secrets.load_license_secrets()

    assert credentials.account_id == "inline-account"
    assert credentials.product_token == "inline-token"
    assert credentials.api_base_url == "https://example.test/accounts/inline-account"


def test_inline_credentials_survive_config_roundtrip(monkeypatch, tmp_path):
    config_path = tmp_path / "video_editor_config.json"
    initial_config = {
        "license_account_id": "roundtrip-account",
        "license_product_token": "roundtrip-token",
        "license_api_base_url": "https://example.test/accounts/roundtrip-account",
        "license_credentials_path": "relative/path/to/credentials.json",
        "ffmpeg_path": "",
    }
    config_path.write_text(json.dumps(initial_config), encoding="utf-8")

    monkeypatch.setattr(gui_constants, "CONFIG_FILE", str(config_path))
    monkeypatch.setattr(config_manager, "CONFIG_FILE", str(config_path))
    monkeypatch.setattr(secrets, "_iter_config_candidates", lambda: (config_path,))

    for env_var in (
        "KEYGEN_LICENSE_BUNDLE",
        "KEYGEN_LICENSE_BUNDLE_PATH",
        "KEYGEN_ACCOUNT_ID",
        "KEYGEN_PRODUCT_TOKEN",
        "KEYGEN_API_BASE_URL",
    ):
        monkeypatch.delenv(env_var, raising=False)

    loaded_config = config_manager.ConfigManager.load_config()

    assert loaded_config["license_account_id"] == "roundtrip-account"
    assert loaded_config["license_product_token"] == "roundtrip-token"
    assert loaded_config["license_credentials_path"] == "relative/path/to/credentials.json"

    config_without_secrets = {
        key: value
        for key, value in loaded_config.items()
        if not key.startswith("license_")
    }
    config_without_secrets["output_folder"] = "some/other/path"

    config_manager.ConfigManager.save_config(config_without_secrets)

    reloaded_config = config_manager.ConfigManager.load_config()
    assert reloaded_config["license_account_id"] == "roundtrip-account"
    assert reloaded_config["license_product_token"] == "roundtrip-token"
    assert reloaded_config["license_api_base_url"] == (
        "https://example.test/accounts/roundtrip-account"
    )
    assert reloaded_config["license_credentials_path"] == "relative/path/to/credentials.json"

    credentials = secrets.load_license_secrets()
    assert credentials.account_id == "roundtrip-account"
    assert credentials.product_token == "roundtrip-token"
    assert credentials.api_base_url == "https://example.test/accounts/roundtrip-account"


def test_load_license_secrets_with_minor_json_error(monkeypatch, tmp_path):
    # Falta uma vírgula entre os campos para simular um ficheiro editado manualmente.
    raw_config = """{
  \"license_account_id\": \"inline-account\"
  \"license_product_token\": \"inline-token\",
  \"license_api_base_url\": \"https://example.test/accounts/inline-account\"
}"""

    config_path = tmp_path / "video_editor_config.json"
    config_path.write_text(raw_config, encoding="utf-8")

    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE", raising=False)
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE_PATH", raising=False)
    monkeypatch.delenv("KEYGEN_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("KEYGEN_PRODUCT_TOKEN", raising=False)

    monkeypatch.setattr(
        secrets,
        "_iter_config_candidates",
        lambda: (config_path,),
    )

    credentials = secrets.load_license_secrets()

    assert credentials.account_id == "inline-account"


def test_persist_inline_credentials_updates_config(monkeypatch, tmp_path):
    config_path = tmp_path / "video_editor_config.json"
    config_path.write_text(json.dumps({"ffmpeg_path": ""}), encoding="utf-8")

    monkeypatch.setattr(secrets, "_iter_config_candidates", lambda: (config_path,))
    monkeypatch.setattr(secrets, "_iter_local_bundle_candidates", lambda: ())
    if hasattr(secrets._load_config_data, "cache_clear"):
        secrets._load_config_data.cache_clear()

    for env_var in (
        "KEYGEN_LICENSE_BUNDLE",
        "KEYGEN_LICENSE_BUNDLE_PATH",
        "KEYGEN_ACCOUNT_ID",
        "KEYGEN_PRODUCT_TOKEN",
        "KEYGEN_API_BASE_URL",
    ):
        monkeypatch.delenv(env_var, raising=False)

    secrets.persist_inline_credentials(
        "new-account",
        "new-token",
        "https://example.test/accounts/new-account",
    )

    stored_config = json.loads(config_path.read_text(encoding="utf-8"))
    assert stored_config["license_account_id"] == "new-account"
    assert stored_config["license_product_token"] == "new-token"
    assert stored_config["license_api_base_url"] == "https://example.test/accounts/new-account"

    credentials = secrets.load_license_secrets()
    assert credentials.account_id == "new-account"
    assert credentials.product_token == "new-token"
    assert credentials.api_base_url == "https://example.test/accounts/new-account"


def test_missing_configuration_raises_error(monkeypatch):
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE", raising=False)
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE_PATH", raising=False)
    monkeypatch.delenv("KEYGEN_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("KEYGEN_PRODUCT_TOKEN", raising=False)

    monkeypatch.setattr(secrets, "_load_bundle_from_local_installation", lambda: None)

    with pytest.raises(secrets.SecretLoaderError) as excinfo:
        secrets.load_license_secrets()

    message = str(excinfo.value)
    lowered = message.lower()
    assert "credenciais" in lowered
    assert "keygen_license_bundle" in lowered


def test_license_checker_exposes_cached_credentials(monkeypatch):
    monkeypatch.setenv("KEYGEN_ACCOUNT_ID", "cached-account")
    monkeypatch.setenv("KEYGEN_PRODUCT_TOKEN", "cached-token")
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE", raising=False)
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE_PATH", raising=False)

    module = _reload_license_checker()

    credentials = module.get_license_service_credentials()
    assert credentials.account_id == "cached-account"
    assert module.get_product_token() == "cached-token"
    assert module.get_api_base_url().endswith("/cached-account")

    # Atualiza o ambiente para garantir que o cache é reutilizado enquanto não for limpo.
    monkeypatch.setenv("KEYGEN_PRODUCT_TOKEN", "updated-token")
    assert module.get_product_token() == "cached-token"

    module.get_license_service_credentials.cache_clear()
    assert module.get_product_token() == "updated-token"


def test_empty_environment_raises_error(monkeypatch):
    monkeypatch.setenv("KEYGEN_LICENSE_BUNDLE", "")
    monkeypatch.setenv("KEYGEN_LICENSE_BUNDLE_PATH", "")
    monkeypatch.setenv("KEYGEN_ACCOUNT_ID", "")
    monkeypatch.setenv("KEYGEN_PRODUCT_TOKEN", "")
    monkeypatch.setenv("KEYGEN_API_BASE_URL", "")

    monkeypatch.setattr(secrets, "_load_bundle_from_local_installation", lambda: None)

    with pytest.raises(secrets.SecretLoaderError):
        secrets.load_license_secrets()


def test_validate_license_with_missing_credentials(monkeypatch):
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE", raising=False)
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE_PATH", raising=False)
    monkeypatch.delenv("KEYGEN_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("KEYGEN_PRODUCT_TOKEN", raising=False)

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
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE", raising=False)
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE_PATH", raising=False)
    monkeypatch.delenv("KEYGEN_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("KEYGEN_PRODUCT_TOKEN", raising=False)

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
