import license_checker
import pytest
import requests


class DummyResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            raise requests.exceptions.HTTPError(response=self)


@pytest.fixture(autouse=True)
def clear_delegated_cache():
    license_checker._clear_delegated_token_cache()
    yield
    license_checker._clear_delegated_token_cache()


def test_activate_new_license_fails_without_delegated_token(monkeypatch):
    monkeypatch.delenv(license_checker.PRODUCT_TOKEN_ENV_VAR, raising=False)
    monkeypatch.delenv(license_checker.PRODUCT_TOKEN_FILE_ENV_VAR, raising=False)
    monkeypatch.delenv(license_checker.TOKEN_BROKER_URL_ENV_VAR, raising=False)
    monkeypatch.delenv(
        license_checker.TOKEN_BROKER_SHARED_SECRET_ENV_VAR, raising=False
    )

    license_checker.get_product_token.cache_clear()

    def fake_request_delegated(_license_key):
        return None, None, "Serviço de credenciais indisponível"

    monkeypatch.setattr(
        license_checker, "_request_delegated_credential", fake_request_delegated
    )

    def fake_post(url, *args, **kwargs):
        if url.endswith("/licenses/actions/validate-key"):
            return DummyResponse(
                {"meta": {"valid": True}, "data": {"id": "lic-123"}}
            )
        raise AssertionError(f"URL inesperada: {url}")

    monkeypatch.setattr(license_checker.requests, "post", fake_post)

    activation_data, message, error_code = license_checker.activate_new_license(
        "AAAA-BBBB-CCCC-DDDD", "fingerprint"
    )

    assert activation_data is None
    assert error_code == "auth_required"
    assert "credencia" in (message or "").lower()
