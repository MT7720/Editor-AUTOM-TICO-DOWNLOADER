import json
from datetime import datetime, timedelta, timezone

import license_checker
import pytest

from gui.app import VideoEditorApp
from security.license_authority import issue_license_token
from ttkbootstrap.dialogs import Messagebox


@pytest.fixture(autouse=True)
def configure_revocation_cache(tmp_path, monkeypatch):
    revocation_file = tmp_path / "revocations.json"
    revocation_file.write_text(json.dumps({"revoked": []}))
    env_var = getattr(license_checker, "LICENSE_REVOCATION_FILE_ENV_VAR", "KEYGEN_LICENSE_REVOCATION_FILE")
    monkeypatch.setenv(env_var, str(revocation_file))
    if hasattr(license_checker, "_clear_revocation_cache"):
        license_checker._clear_revocation_cache()
    yield revocation_file
    if hasattr(license_checker, "_clear_revocation_cache"):
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
    if hasattr(license_checker, "_clear_revocation_cache"):
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

    payload, error, invalidated = license_checker.validate_license_with_id(
        "cust-1", "fingerprint", token
    )
    assert error is None
    assert payload["meta"]["valid"] is True
    assert invalidated is False

    revocation_file.write_text(json.dumps({"revoked": ["serial-42"]}))
    if hasattr(license_checker, "_clear_revocation_cache"):
        license_checker._clear_revocation_cache()

    payload, error, invalidated = license_checker.validate_license_with_id(
        "cust-1", "fingerprint", token
    )
    assert error is None
    assert payload["meta"]["valid"] is False
    assert "revogad" in payload["meta"]["detail"].lower()
    assert invalidated is False


class _DummyRoot:
    def __init__(self):
        self.after_calls = []

    def after(self, delay, callback=None, *args):
        self.after_calls.append((delay, callback, args))
        return f"job-{len(self.after_calls)}"

    def after_cancel(self, job_id):  # pragma: no cover - defensive
        self.after_calls.append(("cancel", job_id))

    def destroy(self):
        self.destroyed = True

    def winfo_exists(self):  # pragma: no cover - defensive
        return True


def test_periodic_check_handles_not_found(monkeypatch):
    monkeypatch.setattr(license_checker, "get_machine_fingerprint", lambda: "fingerprint")

    app = VideoEditorApp.__new__(VideoEditorApp)
    root = _DummyRoot()
    root.destroyed = False
    app.root = root
    app._license_id = "missing-license"
    app._license_fingerprint = "fingerprint"
    app._license_check_job = None
    app._license_check_failures = 0
    app._license_termination_initiated = False
    app.license_data = {"meta": {"key": "stored-key"}}

    detail = "License not found"

    monkeypatch.setattr(
        license_checker,
        "validate_license_with_id",
        lambda *args, **kwargs: ({"meta": {"valid": False, "detail": detail}}, None, True),
    )

    warnings = {}

    def fake_warning(message, title, parent=None):
        warnings["message"] = message
        warnings["title"] = title

    monkeypatch.setattr(Messagebox, "show_warning", fake_warning)

    destroyed = {"called": False}

    def fake_destroy():
        destroyed["called"] = True

    app.root.destroy = fake_destroy

    with pytest.raises(SystemExit) as exc:
        app._run_license_check()

    assert exc.value.code == 1
    assert warnings["message"] == detail
    assert warnings["title"] == "Licença inválida"
    assert destroyed["called"] is True
    assert not root.after_calls
