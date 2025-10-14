import base64
import json
from pathlib import Path

import pytest

import license_checker


@pytest.fixture(autouse=True)
def disable_messagebox(monkeypatch):
    monkeypatch.setattr(license_checker.messagebox, "showerror", lambda *a, **k: None)
    monkeypatch.setattr(license_checker.messagebox, "showwarning", lambda *a, **k: None)


@pytest.fixture
def temp_license_path(tmp_path, monkeypatch):
    license_path = tmp_path / "license.json"
    monkeypatch.setattr(license_checker, "LICENSE_FILE_PATH", str(license_path))
    monkeypatch.setattr(license_checker, "APP_DATA_PATH", tmp_path)
    return license_path


def test_save_and_load_roundtrip(temp_license_path):
    fingerprint = "fingerprint-123"
    license_payload = {"meta": {"key": "ABC-123"}, "data": {"id": "lic-1"}}

    license_checker.save_license_data(license_payload, fingerprint)
    loaded = license_checker.load_license_data(fingerprint)

    assert loaded == license_payload


def test_load_detects_tampered_ciphertext(temp_license_path):
    fingerprint = "fingerprint-987"
    license_payload = {"meta": {"key": "XYZ"}, "data": {"id": "lic-2"}}

    license_checker.save_license_data(license_payload, fingerprint)

    blob = json.loads(Path(temp_license_path).read_text(encoding="utf-8"))
    ciphertext = base64.b64decode(blob["ciphertext"])
    corrupted = bytearray(ciphertext)
    corrupted[0] ^= 0xFF
    blob["ciphertext"] = base64.b64encode(bytes(corrupted)).decode("ascii")
    Path(temp_license_path).write_text(json.dumps(blob), encoding="utf-8")

    with pytest.raises(license_checker.LicenseTamperedError):
        license_checker.load_license_data(fingerprint)
