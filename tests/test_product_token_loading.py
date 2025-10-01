import license_checker


def test_get_product_token_from_embedded_resource(monkeypatch):
    monkeypatch.delenv(license_checker.PRODUCT_TOKEN_ENV_VAR, raising=False)
    monkeypatch.delenv(license_checker.PRODUCT_TOKEN_FILE_ENV_VAR, raising=False)
    license_checker.get_product_token.cache_clear()

    token = license_checker.get_product_token()

    resource_path = license_checker.resource_path(license_checker.PRODUCT_TOKEN_RESOURCE)
    with open(resource_path, "r", encoding="utf-8") as resource_file:
        expected = resource_file.read().strip()

    assert token == expected

    license_checker.get_product_token.cache_clear()
