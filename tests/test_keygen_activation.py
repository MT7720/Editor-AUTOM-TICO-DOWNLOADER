import types

import license_checker
from security import licensing_api


def _configure_credentials(monkeypatch):
    credentials = types.SimpleNamespace(
        api_base_url="https://api.example.test",
        api_token="service-token",
    )
    monkeypatch.setattr(license_checker, "get_license_service_credentials", lambda: credentials)


def test_activate_new_license_success(monkeypatch):
    _configure_credentials(monkeypatch)

    calls = {}

    def fake_validate_license_key(*, base_url, api_token, license_key, timeout=10):
        calls["base_url"] = base_url
        calls["api_token"] = api_token
        calls["license_key"] = license_key
        calls["timeout"] = timeout
        return licensing_api.LicenseAPIResponse(
            status_code=200,
            payload={
                "valid": True,
                "message": "Tudo certo",
                "license": {"id": "license-1"},
                "meta": {"extra": "value"},
            },
        )

    monkeypatch.setattr(license_checker.licensing_api, "validate_license_key", fake_validate_license_key)

    payload, message, detail = license_checker.activate_new_license("KEY-123", "fingerprint-xyz")

    assert payload["meta"]["key"] == "KEY-123"
    assert payload["meta"]["valid"] is True
    assert payload["meta"]["fingerprint"] == "fingerprint-xyz"
    assert payload["license"]["id"] == "license-1"
    assert payload["data"]["id"] == "license-1"
    assert payload["valid"] is True
    assert payload["message"] == "Tudo certo"
    assert "sucesso" in message.lower()
    assert detail is None

    assert calls["base_url"] == "https://api.example.test"
    assert calls["api_token"] == "service-token"
    assert calls["license_key"] == "KEY-123"
    assert calls["timeout"] == 10


def test_activate_new_license_handles_api_error(monkeypatch):
    _configure_credentials(monkeypatch)

    def fake_validate_license_key(**_kwargs):
        return licensing_api.LicenseAPIResponse(
            status_code=404,
            payload={"valid": False, "message": "Licença inválida"},
        )

    monkeypatch.setattr(license_checker.licensing_api, "validate_license_key", fake_validate_license_key)

    payload, message, detail = license_checker.activate_new_license("BAD", "fp")

    assert payload is None
    assert "licença inválida" in message.lower()
    assert detail == "Licença inválida"


def test_activate_new_license_handles_network_error(monkeypatch):
    _configure_credentials(monkeypatch)

    def raise_error(**_kwargs):
        raise licensing_api.LicenseAPINetworkError("timeout")

    monkeypatch.setattr(license_checker.licensing_api, "validate_license_key", raise_error)

    payload, message, detail = license_checker.activate_new_license("KEY-123", "fingerprint")

    assert payload is None
    assert "não foi possível contactar o servidor" in message.lower()
    assert detail is None
