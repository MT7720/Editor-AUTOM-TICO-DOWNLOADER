import json
from datetime import datetime, timedelta, timezone

import pytest

from security.license_authority import issue_license_token
from gui.app import VideoEditorApp
import license_checker


@pytest.fixture(autouse=True)
def configure_revocation_cache(tmp_path, monkeypatch):
    revocation_file = tmp_path / "revocations.json"
    revocation_file.write_text(json.dumps({"revoked": []}))

    env_var_name = getattr(
        license_checker, "LICENSE_REVOCATION_FILE_ENV_VAR", "EDITOR_AUTOMATICO_LICENSE_REVOCATIONS"
    )
    monkeypatch.setenv(env_var_name, str(revocation_file))
    if not hasattr(license_checker, "LICENSE_REVOCATION_FILE_ENV_VAR"):
        monkeypatch.setattr(
            license_checker, "LICENSE_REVOCATION_FILE_ENV_VAR", env_var_name, raising=False
        )

    clear_cache = getattr(license_checker, "_clear_revocation_cache", None)
    if clear_cache is None:
        def _noop():
            return None

        monkeypatch.setattr(license_checker, "_clear_revocation_cache", _noop, raising=False)
        clear_cache = license_checker._clear_revocation_cache

    clear_cache()
    yield revocation_file
    clear_cache()


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
        "legacy.token.com.pontos", "fingerprint"
    )

    assert activation_data is None
    assert error_code == "migration_required"
    assert license_checker.MIGRATION_REQUIRED_MESSAGE in message


def test_activate_new_license_sends_hyphenated_keys_to_keygen(monkeypatch):
    captured = {}

    def fake_validate(key, fingerprint):
        captured["args"] = (key, fingerprint)
        return {"meta": {"valid": True}}, None, None

    monkeypatch.setattr(license_checker, "_validate_key_with_keygen", fake_validate)

    activation_data, message, error_code = license_checker.activate_new_license(
        "AAAA-BBBB-CCCC-DDDD", "fingerprint"
    )

    assert captured["args"] == ("AAAA-BBBB-CCCC-DDDD", "fingerprint")
    assert activation_data == {"meta": {"valid": True}}
    assert message == "Licença ativada com sucesso."
    assert error_code is None


def test_activate_new_license_blocks_revoked_serial(configure_revocation_cache):
    revocation_file = configure_revocation_cache
    token = _valid_token("fingerprint", serial="revoked-serial")
    revocation_file.write_text(json.dumps({"revoked": ["revoked-serial"]}))
    license_checker._clear_revocation_cache()

    activation_data, message, error_code = license_checker.activate_new_license(
        token, "fingerprint"
    )

    assert activation_data is None
    assert error_code == "migration_required"
    assert license_checker.MIGRATION_REQUIRED_MESSAGE in message


def test_activate_new_license_requires_matching_fingerprint():
    token = _valid_token("expected")

    activation_data, message, error_code = license_checker.activate_new_license(
        token, "different"
    )

    assert activation_data is None
    assert error_code == "migration_required"
    assert license_checker.MIGRATION_REQUIRED_MESSAGE in message


def test_validate_license_detects_revocation(configure_revocation_cache):
    revocation_file = configure_revocation_cache
    token = _valid_token("fingerprint", serial="serial-42")

    payload, error, invalid_detail = license_checker.validate_license_key(
        token, "fingerprint"
    )
    assert payload is None
    assert error == license_checker.MIGRATION_REQUIRED_MESSAGE
    assert invalid_detail == "migration_required"

    revocation_file.write_text(json.dumps({"revoked": ["serial-42"]}))
    license_checker._clear_revocation_cache()

    payload, error, invalid_detail = license_checker.validate_license_key(
        token, "fingerprint"
    )
    assert payload is None
    assert error == license_checker.MIGRATION_REQUIRED_MESSAGE
    assert invalid_detail == "migration_required"


def test_check_license_dialog_starts_blank_when_revalidation_fails(monkeypatch):
    monkeypatch.setattr(license_checker, "get_machine_fingerprint", lambda: "fingerprint")
    monkeypatch.setattr(
        license_checker,
        "load_license_data",
        lambda fp: {"data": {"id": "license-id"}, "meta": {"key": "stored"}},
    )

    def fake_validate(license_key, fingerprint):
        assert license_key == "stored"
        return None, "Falha na revalidação", None

    monkeypatch.setattr(license_checker, "validate_license_key", fake_validate)
    monkeypatch.setattr(license_checker, "load_license_secrets", lambda: None)

    logged_messages = []

    def fake_print(*args, **kwargs):
        logged_messages.append(" ".join(str(arg) for arg in args))

    monkeypatch.setattr(license_checker, "print", fake_print, raising=False)

    captured_initial_status = {}

    class DummyDialog:
        def __init__(self, parent, fingerprint, activation_timeout=None, initial_status=None):
            captured_initial_status["value"] = initial_status
            self.cancelled = True
            self.result_data = None

    monkeypatch.setattr(license_checker, "CustomLicenseDialog", DummyDialog)

    success, payload = license_checker.check_license(parent_window=None)

    assert success is False
    assert payload is None
    assert captured_initial_status.get("value") in (None, "")
    assert any(
        "Falha na revalidação" in message for message in logged_messages
    ), "Expected revalidation failure message to be logged"


def test_license_not_found_triggers_termination(monkeypatch):
    class DummyRoot:
        def __init__(self):
            self.after_calls = []

        def after(self, delay, callback=None, *args):
            self.after_calls.append((delay, callback, args))
            return "job"

        def after_cancel(self, job_id):  # pragma: no cover - defensive
            self.after_calls.append(("cancel", job_id))

    monkeypatch.setattr(license_checker, "get_machine_fingerprint", lambda: "fingerprint")
    monkeypatch.setattr(
        license_checker,
        "validate_license_key",
        lambda *args, **kwargs: (None, None, "Licença não encontrada"),
    )

    app = VideoEditorApp.__new__(VideoEditorApp)
    app.root = DummyRoot()
    app._license_key = "stored-key"
    app._license_fingerprint = "fingerprint"
    app._license_check_job = None
    app._license_check_failures = 0
    app._license_termination_initiated = False
    app.license_data = {"meta": {"key": "stored-key"}}

    termination = {}

    def fake_handle(self, detail):
        termination["detail"] = detail

    import types

    app._handle_invalid_license = types.MethodType(fake_handle, app)

    app._run_license_check()

    assert termination["detail"] == "Licença não encontrada"
    assert app.root.after_calls == []
    assert app._license_check_failures == 0
