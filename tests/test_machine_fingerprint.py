import hashlib
import license_checker


class _FailFallback(Exception):
    """Erro auxiliar usado quando a estratégia errada é invocada."""


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_get_machine_fingerprint_uses_machine_guid_first(monkeypatch):
    calls = []

    monkeypatch.setattr(license_checker.platform, "system", lambda: "Windows")

    def machine_guid():
        calls.append("guid")
        return "GUID-A"

    def firmware():  # pragma: no cover - não deve ser chamado neste cenário
        raise _FailFallback("Firmware não deveria ser usado")

    def volume():  # pragma: no cover - não deve ser chamado neste cenário
        raise _FailFallback("Volume não deveria ser usado")

    monkeypatch.setattr(license_checker, "_get_windows_machine_guid", machine_guid)
    monkeypatch.setattr(license_checker, "_get_windows_firmware_uuid", firmware)
    monkeypatch.setattr(license_checker, "_get_windows_volume_serial", volume)
    monkeypatch.setattr(
        license_checker,
        "_get_portable_fingerprint_source",
        lambda: (_ for _ in ()).throw(_FailFallback("Fallback não deveria ser usado")),
    )

    assert license_checker.get_machine_fingerprint() == _hash("GUID-A")
    assert calls == ["guid"]


def test_get_machine_fingerprint_falls_back_to_firmware_uuid(monkeypatch):
    calls = []

    monkeypatch.setattr(license_checker.platform, "system", lambda: "Windows")

    def machine_guid():
        calls.append("guid")
        return None

    def firmware():
        calls.append("firmware")
        return "SMBIOS-UUID"

    def volume():  # pragma: no cover - não deve ser chamado neste cenário
        raise _FailFallback("Volume não deveria ser usado")

    monkeypatch.setattr(license_checker, "_get_windows_machine_guid", machine_guid)
    monkeypatch.setattr(license_checker, "_get_windows_firmware_uuid", firmware)
    monkeypatch.setattr(license_checker, "_get_windows_volume_serial", volume)
    monkeypatch.setattr(
        license_checker,
        "_get_portable_fingerprint_source",
        lambda: (_ for _ in ()).throw(_FailFallback("Fallback não deveria ser usado")),
    )

    assert license_checker.get_machine_fingerprint() == _hash("SMBIOS-UUID")
    assert calls == ["guid", "firmware"]


def test_get_machine_fingerprint_falls_back_to_volume_serial(monkeypatch):
    calls = []

    monkeypatch.setattr(license_checker.platform, "system", lambda: "Windows")

    def machine_guid():
        calls.append("guid")
        return None

    def firmware():
        calls.append("firmware")
        return None

    def volume():
        calls.append("volume")
        return "1234ABCD"

    monkeypatch.setattr(license_checker, "_get_windows_machine_guid", machine_guid)
    monkeypatch.setattr(license_checker, "_get_windows_firmware_uuid", firmware)
    monkeypatch.setattr(license_checker, "_get_windows_volume_serial", volume)
    monkeypatch.setattr(
        license_checker,
        "_get_portable_fingerprint_source",
        lambda: (_ for _ in ()).throw(_FailFallback("Fallback não deveria ser usado")),
    )

    assert license_checker.get_machine_fingerprint() == _hash("1234ABCD")
    assert calls == ["guid", "firmware", "volume"]


def test_get_machine_fingerprint_uses_portable_when_not_windows(monkeypatch):
    monkeypatch.setattr(license_checker.platform, "system", lambda: "Linux")

    def portable():
        return "portable-id"

    monkeypatch.setattr(
        license_checker,
        "_get_portable_fingerprint_source",
        portable,
    )

    assert license_checker.get_machine_fingerprint() == _hash("portable-id")
