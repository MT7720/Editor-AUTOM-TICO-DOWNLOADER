import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("KEYGEN_ACCOUNT_ID", "test-account")
os.environ.setdefault("KEYGEN_PRODUCT_TOKEN", "test-token")


@pytest.fixture(autouse=True)
def configure_license_authority_keys(monkeypatch):
    test_key_file = Path(__file__).with_name("data") / "license_authority_test_keys.json"
    monkeypatch.setenv("LICENSE_AUTHORITY_KEY_FILE", str(test_key_file))
    yield
