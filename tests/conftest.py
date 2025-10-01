import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("KEYGEN_PRODUCT_TOKEN", "test-token")

import license_checker  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_license_storage(monkeypatch, tmp_path):
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    monkeypatch.setattr(license_checker, "APP_DATA_PATH", str(appdata))
    monkeypatch.setattr(license_checker, "LICENSE_FILE_PATH", str(appdata / "license.json"))
    monkeypatch.setattr(license_checker, "USER_PRODUCT_TOKEN_PATH", str(appdata / "product_token.dat"))
    monkeypatch.delenv(license_checker.REVOCATION_URL_ENV_VAR, raising=False)
