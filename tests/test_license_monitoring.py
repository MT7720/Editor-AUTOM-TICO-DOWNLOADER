import pytest

import license_checker
from gui.app import VideoEditorApp
from ttkbootstrap.dialogs import Messagebox


class DummyRoot:
    def __init__(self):
        self.after_calls = []
        self.destroyed = False

    def after(self, delay, callback=None, *args):
        self.after_calls.append((delay, callback, args))
        return f"job-{len(self.after_calls)}"

    def after_cancel(self, job_id):
        self.after_calls.append(("cancel", job_id))

    def destroy(self):
        self.destroyed = True

    def winfo_exists(self):  # pragma: no cover - defensive
        return not self.destroyed


@pytest.fixture
def license_app(monkeypatch):
    monkeypatch.setattr(license_checker, "get_machine_fingerprint", lambda: "fingerprint")

    app = VideoEditorApp.__new__(VideoEditorApp)
    root = DummyRoot()
    app.root = root
    app._license_id = "test-id"
    app._license_fingerprint = "fingerprint"
    app._license_check_job = None
    app._license_check_failures = 0
    app._license_termination_initiated = False
    app.license_data = {"meta": {"key": "stored-key"}}
    app.LICENSE_CHECK_JITTER_FACTOR = 0

    yield app, root.after_calls


def test_periodic_license_validation_success(monkeypatch, license_app):
    app, after_calls = license_app

    def fake_validate(license_id, fingerprint, license_key):
        assert license_id == "test-id"
        assert fingerprint == "fingerprint"
        assert license_key == "stored-key"
        return {"meta": {"valid": True}}, None, False

    monkeypatch.setattr(license_checker, "validate_license_with_id", fake_validate)

    app._run_license_check()

    assert app._license_check_failures == 0
    assert after_calls
    assert after_calls[-1][0] == app.LICENSE_CHECK_INTERVAL_MS


def test_license_validation_network_backoff(monkeypatch, license_app):
    app, after_calls = license_app
    after_calls.clear()

    monkeypatch.setattr(
        license_checker,
        "validate_license_with_id",
        lambda *args, **kwargs: (None, "network-error", False),
    )

    app._run_license_check()

    assert app._license_check_failures == 1
    assert after_calls
    expected_delay = min(
        app.LICENSE_CHECK_INTERVAL_MS * (2 ** app._license_check_failures),
        app.LICENSE_CHECK_MAX_INTERVAL_MS,
    )
    assert after_calls[-1][0] == expected_delay


def test_license_validation_invalid_triggers_exit(monkeypatch, license_app):
    app, after_calls = license_app
    after_calls.clear()

    monkeypatch.setattr(
        license_checker,
        "validate_license_with_id",
        lambda *args, **kwargs: (
            {"meta": {"valid": False, "detail": "Expirada"}},
            None,
            False,
        ),
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
    assert warnings["message"] == "Expirada"
    assert warnings["title"] == "Licença inválida"
    assert destroyed["called"] is True


def test_license_validation_authentication_failure(monkeypatch, license_app):
    app, after_calls = license_app
    after_calls.clear()
    app.license_data = None

    def fake_validate(license_id, fingerprint, license_key):
        assert license_key is None
        return None, "auth-error", False

    monkeypatch.setattr(license_checker, "validate_license_with_id", fake_validate)

    app._run_license_check()

    assert app._license_check_failures == 1
    assert after_calls
    expected_delay = min(
        app.LICENSE_CHECK_INTERVAL_MS * (2 ** app._license_check_failures),
        app.LICENSE_CHECK_MAX_INTERVAL_MS,
    )
    assert after_calls[-1][0] == expected_delay
