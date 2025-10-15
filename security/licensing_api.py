"""Minimal HTTP client for the Automático licensing API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import requests

__all__ = [
    "LicenseAPIError",
    "LicenseAPINetworkError",
    "LicenseAPIInvalidResponseError",
    "LicenseAPIResponse",
    "validate_license_key",
]


class LicenseAPIError(RuntimeError):
    """Base error raised when the licensing API cannot complete a request."""


class LicenseAPINetworkError(LicenseAPIError):
    """Raised when the licensing API cannot be reached."""


class LicenseAPIInvalidResponseError(LicenseAPIError):
    """Raised when the licensing API returns an invalid or unexpected payload."""


@dataclass(frozen=True)
class LicenseAPIResponse:
    """Container for HTTP responses from the licensing API."""

    status_code: int
    payload: Dict[str, Any]


def _build_url(base_url: str) -> str:
    base = (base_url or "").rstrip("/")
    if not base:
        raise LicenseAPIError("O URL do serviço de licenciamento não foi configurado.")
    return f"{base}/licenses/validate"


def validate_license_key(
    *, base_url: str, api_token: str, license_key: str, timeout: int = 10
) -> LicenseAPIResponse:
    """Validate a license key using Automático's licensing API."""

    url = _build_url(base_url)
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    body = {"license_key": license_key}

    try:
        response = requests.post(url, json=body, headers=headers, timeout=timeout)
    except requests.RequestException as exc:  # pragma: no cover - requests guarantees message
        raise LicenseAPINetworkError("Não foi possível contactar o serviço de licenciamento.") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise LicenseAPIInvalidResponseError(
            "Resposta inválida do serviço de licenciamento."
        ) from exc

    if not isinstance(payload, dict):
        raise LicenseAPIInvalidResponseError(
            "Estrutura inesperada devolvida pelo serviço de licenciamento."
        )

    return LicenseAPIResponse(status_code=response.status_code, payload=payload)
