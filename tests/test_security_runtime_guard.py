import types

import pytest

from security import runtime_guard


@pytest.fixture(autouse=True)
def reset_logger_and_modules(monkeypatch, tmp_path):
    runtime_guard._logger = None
    monkeypatch.setattr(runtime_guard, "_resolve_log_path", lambda: tmp_path / "guard.log")
    yield
    runtime_guard._logger = None


def test_enforce_runtime_safety_raises_on_detected_violation(monkeypatch):
    monkeypatch.setattr(runtime_guard, "_collect_resource_violations", lambda manifest: [])
    monkeypatch.setattr(runtime_guard, "_collect_executable_violations", lambda manifest: [])
    monkeypatch.setattr(runtime_guard, "_collect_debugger_violations", lambda: ["debugger"])
    monkeypatch.setattr(runtime_guard, "_collect_instrumentation_violations", lambda: [])

    with pytest.raises(runtime_guard.SecurityViolation) as exc_info:
        runtime_guard.enforce_runtime_safety()

    assert "debugger" in str(exc_info.value)


def test_enforce_runtime_safety_passes_when_all_checks_clear(monkeypatch):
    monkeypatch.setattr(runtime_guard, "_collect_resource_violations", lambda manifest: [])
    monkeypatch.setattr(runtime_guard, "_collect_executable_violations", lambda manifest: [])
    monkeypatch.setattr(runtime_guard, "_collect_debugger_violations", lambda: [])
    monkeypatch.setattr(runtime_guard, "_collect_instrumentation_violations", lambda: [])

    runtime_guard.enforce_runtime_safety()


def test_select_executable_entry_prefers_win32_for_32bit_pyinstaller(monkeypatch):
    executables = {
        "win32": {"hash": "x", "signature": "y"},
        "win_amd64": {"hash": "a", "signature": "b"},
        "default": {"hash": "d", "signature": "e"},
    }

    fake_platform = types.SimpleNamespace(
        architecture=lambda: ("32bit", ""),
        machine=lambda: "AMD64",
    )
    fake_sys = types.SimpleNamespace(platform="win32")

    monkeypatch.setattr(runtime_guard, "platform", fake_platform)
    monkeypatch.setattr(runtime_guard, "sys", fake_sys)

    entry = runtime_guard._select_executable_entry(executables)
    assert entry == executables["win32"]


def test_select_executable_entry_prefers_win_amd64_for_64bit_pyinstaller(monkeypatch):
    executables = {
        "win32": {"hash": "x", "signature": "y"},
        "win_amd64": {"hash": "a", "signature": "b"},
        "default": {"hash": "d", "signature": "e"},
    }

    fake_platform = types.SimpleNamespace(
        architecture=lambda: ("64bit", ""),
        machine=lambda: "AMD64",
    )
    fake_sys = types.SimpleNamespace(platform="win32")

    monkeypatch.setattr(runtime_guard, "platform", fake_platform)
    monkeypatch.setattr(runtime_guard, "sys", fake_sys)

    entry = runtime_guard._select_executable_entry(executables)
    assert entry == executables["win_amd64"]
