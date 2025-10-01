import license_checker


def test_get_product_token_from_embedded_resource(monkeypatch, tmp_path):
    monkeypatch.delenv(license_checker.PRODUCT_TOKEN_ENV_VAR, raising=False)
    monkeypatch.delenv(license_checker.PRODUCT_TOKEN_FILE_ENV_VAR, raising=False)
    license_checker.get_product_token.cache_clear()

    resource_token_path = tmp_path / "product_token.dat"
    expected = "VALID_TEST_TOKEN"
    resource_token_path.write_text(expected, encoding="utf-8")

    original_resource_path = license_checker.resource_path

    def fake_resource_path(relative_path):
        if relative_path == license_checker.PRODUCT_TOKEN_RESOURCE:
            return str(resource_token_path)
        return original_resource_path(relative_path)

    monkeypatch.setattr(license_checker, "resource_path", fake_resource_path)

    token = license_checker.get_product_token()

    assert token == expected

    license_checker.get_product_token.cache_clear()
