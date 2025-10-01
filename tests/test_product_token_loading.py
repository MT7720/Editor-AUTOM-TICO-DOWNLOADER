import license_checker
import pytest


def test_get_product_token_from_env(monkeypatch):
    monkeypatch.setenv(license_checker.PRODUCT_TOKEN_ENV_VAR, "VALID_TEST_TOKEN")
    license_checker.get_product_token.cache_clear()

    token = license_checker.get_product_token()

    assert token == "VALID_TEST_TOKEN"

    license_checker.get_product_token.cache_clear()


def test_get_product_token_requires_configuration(monkeypatch, tmp_path):
    monkeypatch.delenv(license_checker.PRODUCT_TOKEN_ENV_VAR, raising=False)
    monkeypatch.delenv(license_checker.PRODUCT_TOKEN_FILE_ENV_VAR, raising=False)

    dummy_user_token_path = tmp_path / "product_token.dat"
    monkeypatch.setattr(
        license_checker, "USER_PRODUCT_TOKEN_PATH", str(dummy_user_token_path)
    )
    license_checker.get_product_token.cache_clear()

    with pytest.raises(RuntimeError):
        license_checker.get_product_token()

    license_checker.get_product_token.cache_clear()
