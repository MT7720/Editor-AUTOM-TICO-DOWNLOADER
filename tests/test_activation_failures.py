import json
from datetime import datetime, timedelta, timezone

import license_checker
import pytest

from security.license_authority import issue_license_token


@pytest.fixture(autouse=True)
def configure_revocation_cache(tmp_path, monkeypatch):
    revocation_file = tmp_path / "revocations.json"
    revocation_file.write_text(json.dumps({"revoked": []}))
    monkeypatch.setenv(license_checker.LICENSE_REVOCATION_FILE_ENV_VAR, str(revocation_file))
    license_checker._clear_revocation_cache()
    yield revocation_file
    license_checker._clear_revocation_cache()


def _valid_token(fingerprint: str, serial: str = "serial-1") -> str:
    expiry = datetime.now(timezone.utc) + timedelta(days=30)
    return issue_license_token(
        customer_id="cust-1",
        fingerprint=fingerprint,
        expiry=expiry,
        seats=1,
        serial=serial,
    )


def test_activate_new_license_rejects_legacy_key():
    activation_data, message, error_code = license_checker.activate_new_license(
        "AAAA-BBBB-CCCC-DDDD", "fingerprint"
    )

    assert activation_data is None
    assert error_code == "migration_required"
    assert license_checker.MIGRATION_REQUIRED_MESSAGE in message


def test_activate_new_license_blocks_revoked_serial(configure_revocation_cache):
    revocation_file = configure_revocation_cache
    token = _valid_token("fingerprint", serial="revoked-serial")
    revocation_file.write_text(json.dumps({"revoked": ["revoked-serial"]}))
    license_checker._clear_revocation_cache()

    activation_data, message, error_code = license_checker.activate_new_license(
        token, "fingerprint"
    )

    assert activation_data is None
    assert error_code is None
    assert "revogad" in message.lower()


def test_activate_new_license_requires_matching_fingerprint():
    token = _valid_token("expected")

    activation_data, message, error_code = license_checker.activate_new_license(
        token, "different"
    )

    assert activation_data is None
    assert error_code is None
    assert "não corresponde" in message.lower()


def test_validate_license_detects_revocation(configure_revocation_cache):
    revocation_file = configure_revocation_cache
    token = _valid_token("fingerprint", serial="serial-42")

    payload, error = license_checker.validate_license_with_id(
        "cust-1", "fingerprint", token
    )
    assert error is None
    assert payload["meta"]["valid"] is True

    revocation_file.write_text(json.dumps({"revoked": ["serial-42"]}))
    license_checker._clear_revocation_cache()

    payload, error = license_checker.validate_license_with_id(
        "cust-1", "fingerprint", token
    )
    assert error is None
    assert payload["meta"]["valid"] is False
    assert "revogad" in payload["meta"]["detail"].lower()
