import types

import license_checker


class _DummyResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _configure_credentials(monkeypatch):
    credentials = types.SimpleNamespace(
        api_base_url="https://api.example.test",
        product_token="product-token",
    )
    monkeypatch.setattr(license_checker, "get_license_service_credentials", lambda: credentials)


def test_activate_new_license_success(monkeypatch):
    _configure_credentials(monkeypatch)

    calls = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["url"] = url
        calls["json"] = json
        calls["headers"] = headers
        calls["timeout"] = timeout
        return _DummyResponse(200, {"data": {"id": "license-1"}, "meta": {"valid": True}})

    monkeypatch.setattr(license_checker.requests, "post", fake_post)

    payload, message, detail = license_checker.activate_new_license("KEY-123", "fingerprint-xyz")

    assert payload["meta"]["key"] == "KEY-123"
    assert payload["meta"]["valid"] is True
    assert payload["meta"]["fingerprint"] == "fingerprint-xyz"
    assert payload["data"]["id"] == "license-1"
    assert "sucesso" in message.lower()
    assert detail is None

    assert calls["url"] == "https://api.example.test/licenses/actions/validate-key"
    assert calls["json"] == {
        "data": {"type": "licenses"},
        "meta": {"key": "KEY-123", "fingerprint": "fingerprint-xyz"},
    }
    assert calls["headers"]["Authorization"] == "Bearer product-token"
    assert calls["headers"]["Accept"] == "application/vnd.api+json"
    assert calls["headers"]["Content-Type"] == "application/vnd.api+json"
    assert calls["timeout"] == 10


def test_activate_new_license_handles_api_error(monkeypatch):
    _configure_credentials(monkeypatch)

    response = _DummyResponse(
        404,
        {"errors": [{"detail": "Licença inválida", "code": "LICENSE_NOT_FOUND"}]},
    )
    monkeypatch.setattr(license_checker.requests, "post", lambda *args, **kwargs: response)

    payload, message, detail = license_checker.activate_new_license("BAD", "fp")

    assert payload is None
    assert "licença inválida" in message.lower()
    assert detail == "Licença inválida"


def test_activate_new_license_handles_network_error(monkeypatch):
    _configure_credentials(monkeypatch)

    def raise_error(*_args, **_kwargs):
        raise license_checker.requests.RequestException("timeout")

    monkeypatch.setattr(license_checker.requests, "post", raise_error)

    payload, message, detail = license_checker.activate_new_license("KEY-123", "fingerprint")

    assert payload is None
    assert "não foi possível contactar o servidor" in message.lower()
    assert detail is None
