import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import license_checker
from security import license_authority
from cryptography.hazmat.primitives import serialization


@pytest.fixture()
def private_key():
    key_path = Path(__file__).parent / "fixtures" / "license_private_test.pem"
    return serialization.load_pem_private_key(key_path.read_bytes(), password=None)


def _issue_token(private_key, *, fingerprint, customer_id="cust-001", license_id="lic-001", serial=1, expiry=None, seat_count=1):
    return license_authority.issue_license_token(
        customer_id=customer_id,
        fingerprint=fingerprint,
        seat_count=seat_count,
        expiry=expiry,
        license_id=license_id,
        serial=serial,
        private_key=private_key,
    )


def test_validate_license_with_valid_token(private_key):
    fingerprint = "machine-fp"
    expiry = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    token = _issue_token(
        private_key,
        fingerprint=fingerprint,
        license_id="lic-valid",
        serial=5,
        expiry=expiry,
        seat_count=3,
    )

    payload, error = license_checker.validate_license_with_id("lic-valid", fingerprint, token)

    assert error is None
    assert payload["meta"]["valid"] is True
    assert payload["data"]["id"] == "lic-valid"
    assert payload["data"]["attributes"]["seatCount"] == 3


def test_validate_license_rejects_other_fingerprint(private_key):
    fingerprint = "machine-fp"
    token = _issue_token(private_key, fingerprint=fingerprint)

    payload, error = license_checker.validate_license_with_id("lic-001", "other-fp", token)

    assert error is None
    assert payload["meta"]["valid"] is False
    assert "outra máquina" in payload["meta"]["detail"]


def test_validate_license_checks_expiry(private_key):
    fingerprint = "machine-fp"
    past_expiry = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    token = _issue_token(private_key, fingerprint=fingerprint, expiry=past_expiry)

    payload, error = license_checker.validate_license_with_id("lic-001", fingerprint, token)

    assert error is None
    assert payload["meta"]["valid"] is False
    assert "expirada" in payload["meta"]["detail"].lower()


def test_validate_license_uses_revocation_list(private_key, tmp_path, monkeypatch):
    fingerprint = "machine-fp"
    token = _issue_token(private_key, fingerprint=fingerprint, license_id="lic-reissue", serial=1)

    revocations = {
        "minimum_serial": {"lic-reissue": 3},
        "revoked": [],
        "revoked_tokens": [],
    }
    revocation_file = tmp_path / "revocations.json"
    revocation_file.write_text(json.dumps(revocations), encoding="utf-8")
    monkeypatch.setenv(license_checker.REVOCATION_URL_ENV_VAR, str(revocation_file))

    payload, error = license_checker.validate_license_with_id(
        "lic-reissue", fingerprint, token, force_refresh=True
    )

    assert error is None
    assert payload["meta"]["valid"] is False
    assert "reemiss" in payload["meta"]["detail"].lower()


def test_validate_license_revoked_token_hash(private_key, tmp_path, monkeypatch):
    fingerprint = "machine-fp"
    token = _issue_token(private_key, fingerprint=fingerprint, license_id="lic-token", serial=7)

    revoked_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    revocations = {"revoked_tokens": [revoked_hash]}
    revocation_file = tmp_path / "revocations.json"
    revocation_file.write_text(json.dumps(revocations), encoding="utf-8")
    monkeypatch.setenv(license_checker.REVOCATION_URL_ENV_VAR, str(revocation_file))

    payload, error = license_checker.validate_license_with_id(
        "lic-token", fingerprint, token, force_refresh=True
    )

    assert error is None
    assert payload["meta"]["valid"] is False
    assert "revogada" in payload["meta"]["detail"].lower()
