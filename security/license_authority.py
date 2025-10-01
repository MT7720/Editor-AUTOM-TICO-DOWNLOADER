"""Utilities for issuing and signing offline license tokens.

This module centralises the logic required to mint compact license tokens that
can be validated by :mod:`license_checker` without having to contact external
services.  The implementation relies on an Ed25519 key pair stored alongside the
application assets.  The private key should only live on trusted build or
operations machines whereas the public key is embedded in the client so it can
verify signatures offline.

The module also exposes a small CLI that can be used to issue multiple licenses
from a CSV file.  Example usage::

    python -m security.license_authority --input licenses.csv --output tokens.json

Each CSV row must contain the columns ``customer_id``, ``fingerprint``,
``expiry`` (ISO 8601 timestamp) and ``seats``.  A ``serial`` column is optional;
if omitted a secure random serial will be generated automatically.
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

__all__ = [
    "LicenseClaims",
    "LicenseAuthority",
    "issue_license_token",
    "load_private_key",
    "load_public_key",
]

_KEY_FILE_ENV_VAR = "LICENSE_AUTHORITY_KEY_FILE"
_DEFAULT_KEY_FILE = Path(__file__).with_name("license_authority_keys.json")


class LicenseKeyError(RuntimeError):
    """Raised when the signing key material cannot be loaded."""


@dataclass(frozen=True)
class LicenseClaims:
    """Structured data that is signed into the compact token."""

    customer_id: str
    fingerprint: str
    expiry: datetime
    seats: int
    serial: str
    issued_at: datetime
    product: str = "editor-automatico"

    def to_json_payload(self) -> Dict[str, object]:
        return {
            "customer_id": self.customer_id,
            "fingerprint": self.fingerprint,
            "exp": self.expiry.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "iat": self.issued_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "seats": self.seats,
            "serial": self.serial,
            "product": self.product,
        }


def _read_key_material() -> Dict[str, str]:
    key_file = Path(os.getenv(_KEY_FILE_ENV_VAR, str(_DEFAULT_KEY_FILE)))
    if not key_file.exists():
        raise LicenseKeyError(f"Ficheiro de chaves não encontrado em {key_file!s}.")
    try:
        with key_file.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - defensive
        raise LicenseKeyError("Não foi possível ler o ficheiro de chaves da autoridade de licenças.") from exc
    if "private_key" not in data or "public_key" not in data:
        raise LicenseKeyError("Formato inválido do ficheiro de chaves da autoridade de licenças.")
    return data


def load_private_key() -> ed25519.Ed25519PrivateKey:
    """Return the Ed25519 private key configured for signing."""

    data = _read_key_material()
    private_bytes = base64.b64decode(data["private_key"])
    return ed25519.Ed25519PrivateKey.from_private_bytes(private_bytes)


def load_public_key() -> ed25519.Ed25519PublicKey:
    """Return the Ed25519 public key for signature verification."""

    data = _read_key_material()
    public_bytes = base64.b64decode(data["public_key"])
    return ed25519.Ed25519PublicKey.from_public_bytes(public_bytes)


class LicenseAuthority:
    """Small helper that signs :class:`LicenseClaims` into compact tokens."""

    def __init__(self, private_key: Optional[ed25519.Ed25519PrivateKey] = None):
        self._private_key = private_key or load_private_key()

    def sign(self, claims: LicenseClaims) -> str:
        payload = json.dumps(claims.to_json_payload(), separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = self._private_key.sign(payload)
        return _encode_compact_token(payload, signature)


def _encode_compact_token(payload: bytes, signature: bytes) -> str:
    payload_segment = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    signature_segment = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{payload_segment}.{signature_segment}"


def issue_license_token(
    customer_id: str,
    fingerprint: str,
    expiry: datetime,
    seats: int,
    serial: Optional[str] = None,
    issued_at: Optional[datetime] = None,
    product: str = "editor-automatico",
    authority: Optional[LicenseAuthority] = None,
) -> str:
    """Return a signed compact token for the provided license attributes."""

    serial = serial or secrets.token_hex(8)
    issued_at = issued_at or datetime.now(timezone.utc)
    authority = authority or LicenseAuthority()
    claims = LicenseClaims(
        customer_id=customer_id,
        fingerprint=fingerprint,
        expiry=expiry,
        seats=seats,
        serial=serial,
        issued_at=issued_at,
        product=product,
    )
    return authority.sign(claims)


def _load_claims_from_row(
    row: Dict[str, str], product: str = "editor-automatico"
) -> LicenseClaims:
    try:
        expiry = datetime.fromisoformat(row["expiry"]).astimezone(timezone.utc)
    except KeyError as exc:
        raise ValueError("A coluna 'expiry' é obrigatória no ficheiro CSV.") from exc
    except ValueError as exc:  # pragma: no cover - input validation
        raise ValueError("Formato inválido para a data de expiração. Utilize ISO 8601.") from exc

    issued_at = datetime.now(timezone.utc)
    serial = row.get("serial") or secrets.token_hex(8)
    seats = int(row.get("seats", "1"))
    customer_id = row.get("customer_id")
    fingerprint = row.get("fingerprint")
    if not customer_id or not fingerprint:
        raise ValueError("As colunas 'customer_id' e 'fingerprint' são obrigatórias.")

    return LicenseClaims(
        customer_id=customer_id,
        fingerprint=fingerprint,
        expiry=expiry,
        seats=seats,
        serial=serial,
        issued_at=issued_at,
        product=product,
    )


def _load_rows(csv_path: Path) -> Iterable[Dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            yield row


def _cli(args: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Gerador de tokens de licença offline")
    parser.add_argument("--input", required=True, help="Caminho para o CSV com as licenças a emitir")
    parser.add_argument(
        "--output",
        required=True,
        help="Ficheiro JSON onde os tokens emitidos serão guardados",
    )
    parser.add_argument(
        "--product",
        default="editor-automatico",
        help="Identificador do produto a incluir nos tokens (opcional)",
    )
    parsed = parser.parse_args(args=args)

    authority = LicenseAuthority()

    tokens: List[Dict[str, str]] = []
    for row in _load_rows(Path(parsed.input)):
        claims = _load_claims_from_row(row, product=parsed.product)
        token = authority.sign(claims)
        tokens.append({"token": token, "customer_id": claims.customer_id, "serial": claims.serial})

    output_path = Path(parsed.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(tokens, handle, indent=2, ensure_ascii=False)

    return 0


def verify_token(token: str, public_key: Optional[ed25519.Ed25519PublicKey] = None) -> Dict[str, object]:
    """Verify a compact token and return the decoded claims."""

    public_key = public_key or load_public_key()
    try:
        payload_segment, signature_segment = token.split(".")
    except ValueError as exc:
        raise ValueError("Token de licença inválido.") from exc
    payload = _decode_segment(payload_segment)
    signature = _decode_segment(signature_segment)
    try:
        public_key.verify(signature, payload)
    except InvalidSignature as exc:
        raise ValueError("Assinatura inválida para o token fornecido.") from exc
    return json.loads(payload.decode("utf-8"))


def _decode_segment(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(_cli())
