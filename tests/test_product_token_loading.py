import base64
import importlib
import json
import os
import sys

import pytest

from security import secrets


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

    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE", raising=False)
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE_PATH", raising=False)
    monkeypatch.delenv("KEYGEN_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("KEYGEN_PRODUCT_TOKEN", raising=False)
    monkeypatch.setattr(
        secrets,
        "_iter_local_bundle_candidates",
        lambda: (bundle_path,),
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


def test_missing_configuration_uses_embedded_defaults(monkeypatch):
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE", raising=False)
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE_PATH", raising=False)
    monkeypatch.delenv("KEYGEN_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("KEYGEN_PRODUCT_TOKEN", raising=False)

    monkeypatch.setattr(secrets, "_load_bundle_from_local_installation", lambda: None)

    credentials = secrets.load_license_secrets()

    assert credentials.account_id == secrets.DEFAULT_LICENSE_CREDENTIALS["account_id"]
    assert credentials.product_token == secrets.DEFAULT_LICENSE_CREDENTIALS["product_token"]
    assert (
        credentials.api_base_url
        == secrets.DEFAULT_LICENSE_CREDENTIALS["api_base_url"]
    )


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


def test_embedded_fallback_is_used_when_env_cleared(monkeypatch):
    monkeypatch.setenv("KEYGEN_LICENSE_BUNDLE", "")
    monkeypatch.setenv("KEYGEN_LICENSE_BUNDLE_PATH", "")
    monkeypatch.setenv("KEYGEN_ACCOUNT_ID", "")
    monkeypatch.setenv("KEYGEN_PRODUCT_TOKEN", "")
    monkeypatch.setenv("KEYGEN_API_BASE_URL", "")

    monkeypatch.setattr(secrets, "_load_bundle_from_local_installation", lambda: None)

    credentials = secrets.load_license_secrets()

    assert credentials.account_id == secrets.DEFAULT_LICENSE_CREDENTIALS["account_id"]
    assert credentials.product_token == secrets.DEFAULT_LICENSE_CREDENTIALS["product_token"]
    assert (
        credentials.api_base_url
        == secrets.DEFAULT_LICENSE_CREDENTIALS["api_base_url"]
    )


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

    payload, error = module.validate_license_with_id("any", "fingerprint")

    assert payload is None
    assert "credenciais" in error.lower()


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

    activation_data, message = module.activate_new_license("token", "fingerprint")

    assert activation_data is None
    assert "credenciais" in message.lower()
