import base64
import hashlib
import hmac
import types
from pathlib import Path

import pytest

from security import runtime_guard


TEST_HMAC_KEY = b"runtime-guard-test-key"


@pytest.fixture(autouse=True)
def reset_logger_and_modules(monkeypatch, tmp_path):
    runtime_guard._logger = None
    monkeypatch.setattr(runtime_guard, "_hmac_key_cache", runtime_guard._HMAC_KEY_UNINITIALIZED)
    monkeypatch.setattr(runtime_guard, "_resolve_log_path", lambda: tmp_path / "guard.log")
    encoded_key = base64.b64encode(TEST_HMAC_KEY).decode()
    monkeypatch.setenv("RUNTIME_GUARD_HMAC_KEY", encoded_key)
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


def test_collect_resource_violations_accepts_crlf_when_normalizing(monkeypatch, tmp_path):
    original_path = Path("license_checker.py")
    lf_copy = tmp_path / "license_checker_lf.py"
    lf_copy.write_bytes(original_path.read_bytes())

    crlf_copy = tmp_path / "license_checker_crlf.py"
    crlf_copy.write_bytes(lf_copy.read_bytes().replace(b"\n", b"\r\n"))

    base_resource = runtime_guard.MANIFEST["resources"]["license_checker.py"].copy()
    base_resource["normalize_newlines"] = True

    algorithm = runtime_guard.MANIFEST.get("algorithm", "sha256")

    manifest_template = {
        "algorithm": algorithm,
        "resources": {"license_checker.py": base_resource},
    }

    def fake_resolve_path(resource):
        return Path(resource["path"])

    monkeypatch.setattr(runtime_guard, "_resolve_resource_path", fake_resolve_path)

    manifest_lf = {
        **manifest_template,
        "resources": {
            "license_checker.py": {
                **base_resource,
                "path": str(lf_copy),
            }
        },
    }

    manifest_crlf = {
        **manifest_template,
        "resources": {
            "license_checker.py": {
                **base_resource,
                "path": str(crlf_copy),
            }
        },
    }

    assert runtime_guard._collect_resource_violations(manifest_lf) == []
    assert runtime_guard._collect_resource_violations(manifest_crlf) == []


def test_collect_resource_violations_skipped_when_not_frozen(monkeypatch):
    fake_sys = types.SimpleNamespace(frozen=False)
    monkeypatch.setattr(runtime_guard, "sys", fake_sys)

    manifest = {
        "resources": {
            "example": {
                "path": "missing",
                "hash": "abc",
                "signature": "def",
            }
        }
    }

    assert runtime_guard._collect_resource_violations(manifest) == []


def test_collect_resource_violations_enforced_when_frozen(monkeypatch, tmp_path):
    fake_sys = types.SimpleNamespace(frozen=True)
    monkeypatch.setattr(runtime_guard, "sys", fake_sys)

    resource_path = tmp_path / "resource.txt"
    resource_path.write_text("conteudo")

    wrong_hash = "0" * 64
    signature = hmac.new(TEST_HMAC_KEY, wrong_hash.encode("utf-8"), hashlib.sha256).hexdigest()

    manifest = {
        "algorithm": "sha256",
        "resources": {
            "resource.txt": {
                "path": str(resource_path),
                "hash": wrong_hash,
                "signature": signature,
            }
        },
    }

    monkeypatch.setattr(runtime_guard, "_resolve_resource_path", lambda resource: Path(resource["path"]))

    violations = runtime_guard._collect_resource_violations(manifest)
    assert violations
    assert "Hash divergente" in violations[0]


def test_collect_resource_violations_fail_when_key_missing(monkeypatch, tmp_path):
    fake_sys = types.SimpleNamespace(frozen=True)
    monkeypatch.setattr(runtime_guard, "sys", fake_sys)

    monkeypatch.delenv("RUNTIME_GUARD_HMAC_KEY", raising=False)
    monkeypatch.setattr(runtime_guard, "_hmac_key_cache", runtime_guard._HMAC_KEY_UNINITIALIZED)

    manifest = {
        "algorithm": "sha256",
        "resources": {
            "example": {
                "path": str(tmp_path / "resource.txt"),
                "hash": "123",
                "signature": "abc",
            }
        },
    }

    violations = runtime_guard._collect_resource_violations(manifest)
    assert violations
    assert "Chave de assinatura" in violations[0]
