from datetime import datetime, timedelta, timezone

import license_checker
from security.license_authority import issue_license_token


class _DummyResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_activate_legacy_license_migrates_success(monkeypatch):
    fingerprint = "fingerprint-123"
    expiry = datetime.now(timezone.utc) + timedelta(days=30)
    token = issue_license_token(
        customer_id="cust-legacy",
        fingerprint=fingerprint,
        expiry=expiry,
        seats=2,
        serial="serial-legacy",
    )

    called = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        called["url"] = url
        called["json"] = json
        called["headers"] = headers
        called["timeout"] = timeout
        return _DummyResponse(
            200,
            {
                "token": token,
                "license": "cust-legacy",
                "serial": "serial-legacy",
                "seats": 2,
                "expiry": expiry.isoformat(),
            },
        )

    migration_url = "https://example.test/migrate"
    monkeypatch.setenv(license_checker.LEGACY_LICENSE_MIGRATION_URL_ENV_VAR, migration_url)
    monkeypatch.setattr(license_checker, "_get_delegated_credential", lambda key: ("delegated-token", None))
    monkeypatch.setattr(license_checker.requests, "post", fake_post)

    activation_data, message, error_code = license_checker.activate_new_license(
        "AAAA-BBBB-CCCC-DDDD", fingerprint
    )

    assert activation_data["meta"]["valid"] is True
    assert activation_data["meta"]["key"] == token
    assert activation_data["meta"]["legacy_key"] == "AAAA-BBBB-CCCC-DDDD"
    assert activation_data["data"]["id"] == "cust-legacy"
    assert "migrada" in message.lower()
    assert error_code is None

    assert called["url"] == migration_url
    assert called["json"] == {
        "licenseKey": "AAAA-BBBB-CCCC-DDDD",
        "fingerprint": fingerprint,
    }
    assert called["headers"]["Authorization"] == "Bearer delegated-token"
    assert called["timeout"] == license_checker.LEGACY_LICENSE_MIGRATION_TIMEOUT


def test_activate_legacy_license_reports_service_error(monkeypatch):
    monkeypatch.setenv(
        license_checker.LEGACY_LICENSE_MIGRATION_URL_ENV_VAR,
        "https://example.test/migrate",
    )
    monkeypatch.setattr(license_checker, "_get_delegated_credential", lambda key: ("token", None))
    monkeypatch.setattr(
        license_checker.requests,
        "post",
        lambda *args, **kwargs: _DummyResponse(422, {"error": "invalid"}),
    )

    activation_data, message, error_code = license_checker.activate_new_license(
        "AAAA-BBBB-CCCC-DDDD", "fingerprint"
    )

    assert activation_data is None
    assert "invalid" in message.lower()
    assert error_code == "migration_required"


def test_activate_legacy_license_requires_service(monkeypatch):
    monkeypatch.delenv(license_checker.LEGACY_LICENSE_MIGRATION_URL_ENV_VAR, raising=False)

    activation_data, message, error_code = license_checker.activate_new_license(
        "AAAA-BBBB-CCCC-DDDD", "fingerprint"
    )

    assert activation_data is None
    assert error_code == "migration_required"
    assert license_checker.MIGRATION_REQUIRED_MESSAGE in message
