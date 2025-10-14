import base64
import importlib
import json
import sys

import pytest

from security import secrets


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


def test_missing_configuration_raises(monkeypatch):
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE", raising=False)
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE_PATH", raising=False)
    monkeypatch.delenv("KEYGEN_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("KEYGEN_PRODUCT_TOKEN", raising=False)

    with pytest.raises(secrets.SecretLoaderError):
        secrets.load_license_secrets()


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


def test_validate_license_with_missing_credentials(monkeypatch):
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE", raising=False)
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE_PATH", raising=False)
    monkeypatch.delenv("KEYGEN_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("KEYGEN_PRODUCT_TOKEN", raising=False)

    module = _reload_license_checker()

    payload, error = module.validate_license_with_id("any", "fingerprint")

    assert payload is None
    assert "credenciais" in error.lower()


def test_activate_new_license_with_missing_credentials(monkeypatch):
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE", raising=False)
    monkeypatch.delenv("KEYGEN_LICENSE_BUNDLE_PATH", raising=False)
    monkeypatch.delenv("KEYGEN_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("KEYGEN_PRODUCT_TOKEN", raising=False)

    module = _reload_license_checker()

    activation_data, message = module.activate_new_license("token", "fingerprint")

    assert activation_data is None
    assert "credenciais" in message.lower()
