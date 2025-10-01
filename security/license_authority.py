"""Utilities for issuing offline license tokens.

This module provides helpers for loading the Ed25519 key pair used by the
licensing authority and for generating signed license tokens.  A small CLI is
included so support teams can automate bulk issuance flows.
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, MutableMapping, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

TOKEN_VERSION = "LA1"
PRIVATE_KEY_PATH_ENV = "LICENSE_AUTHORITY_PRIVATE_KEY_PATH"
PUBLIC_KEY_PATH_ENV = "LICENSE_AUTHORITY_PUBLIC_KEY_PATH"
_DEFAULT_PRIVATE_KEY = Path(__file__).with_name("license_private_key.pem")
_DEFAULT_PUBLIC_KEY = Path(__file__).with_name("license_public_key.pem")


def _load_private_key_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:  # pragma: no cover - defensive
        raise FileNotFoundError(
            f"Não foi possível encontrar a chave privada da autoridade de licenças em {path}."
        ) from exc


def _load_public_key_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:  # pragma: no cover - defensive
        raise FileNotFoundError(
            f"Não foi possível encontrar a chave pública da autoridade de licenças em {path}."
        ) from exc


def load_private_key(path: Optional[os.PathLike[str] | str] = None) -> Ed25519PrivateKey:
    """Load the Ed25519 private key used for signing license tokens."""

    candidate = Path(
        path
        or os.getenv(PRIVATE_KEY_PATH_ENV)
        or _DEFAULT_PRIVATE_KEY
    )
    key_bytes = _load_private_key_bytes(candidate)
    return serialization.load_pem_private_key(key_bytes, password=None)


def load_public_key(path: Optional[os.PathLike[str] | str] = None) -> Ed25519PublicKey:
    """Load the Ed25519 public key paired with :func:`load_private_key`."""

    candidate = Path(
        path
        or os.getenv(PUBLIC_KEY_PATH_ENV)
        or _DEFAULT_PUBLIC_KEY
    )
    key_bytes = _load_public_key_bytes(candidate)
    return serialization.load_pem_public_key(key_bytes)


@dataclass
class LicenseClaims:
    """Normalized payload for a license token."""

    customer_id: str
    fingerprint: str
    seat_count: int = 1
    expiry: Optional[str] = None
    license_id: Optional[str] = None
    serial: int = 1
    issued_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: MutableMapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "customer_id": self.customer_id,
            "fingerprint": self.fingerprint,
            "seat_count": int(self.seat_count),
            "serial": int(self.serial),
            "issued_at": self.issued_at,
        }
        if self.expiry:
            payload["expiry"] = self.expiry
        if self.license_id:
            payload["license_id"] = self.license_id
        if self.metadata:
            payload["meta"] = dict(self.metadata)
        return payload


def _urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _prepare_payload(claims: Mapping[str, Any]) -> bytes:
    return json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_license_claims(
    claims: Mapping[str, Any],
    *,
    private_key: Optional[Ed25519PrivateKey] = None,
) -> str:
    """Sign *claims* and return a compact token."""

    private_key = private_key or load_private_key()
    payload = _prepare_payload(claims)
    signature = private_key.sign(payload)
    return f"{TOKEN_VERSION}.{_urlsafe_b64encode(payload)}.{_urlsafe_b64encode(signature)}"


def issue_license_token(
    *,
    customer_id: str,
    fingerprint: str,
    seat_count: int = 1,
    expiry: Optional[str] = None,
    license_id: Optional[str] = None,
    serial: int = 1,
    metadata: Optional[Mapping[str, Any]] = None,
    private_key: Optional[Ed25519PrivateKey] = None,
) -> str:
    """Create a signed license token for a single customer."""

    claims = LicenseClaims(
        customer_id=customer_id,
        fingerprint=fingerprint,
        seat_count=seat_count,
        expiry=expiry,
        license_id=license_id,
        serial=serial,
        metadata=dict(metadata or {}),
    )
    return sign_license_claims(claims.to_dict(), private_key=private_key)


def _iter_csv_rows(path: Path) -> Iterator[Mapping[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            yield row


def bulk_issue_from_csv(
    input_path: os.PathLike[str] | str,
    *,
    output_path: os.PathLike[str] | str,
    default_seat_count: int = 1,
    default_serial: int = 1,
    private_key: Optional[Ed25519PrivateKey] = None,
) -> List[Dict[str, Any]]:
    """Generate license tokens for every record in *input_path*.

    The CSV file must provide ``customer_id`` and ``fingerprint`` columns.  The
    optional ``expiry`` (ISO 8601), ``seat_count``, ``license_id`` and
    ``serial`` columns override the defaults.  The resulting records are written
    to *output_path* as JSON for downstream automation steps.
    """

    private_key = private_key or load_private_key()
    input_path = Path(input_path)
    output_path = Path(output_path)

    tokens: List[Dict[str, Any]] = []
    for row in _iter_csv_rows(input_path):
        try:
            customer_id = row["customer_id"].strip()
            fingerprint = row["fingerprint"].strip()
        except KeyError as exc:
            raise ValueError(
                "O ficheiro CSV deve conter as colunas 'customer_id' e 'fingerprint'."
            ) from exc

        seat_count = int(row.get("seat_count") or default_seat_count)
        serial = int(row.get("serial") or default_serial)
        expiry = (row.get("expiry") or None) or None
        license_id = (row.get("license_id") or None) or None

        claims = LicenseClaims(
            customer_id=customer_id,
            fingerprint=fingerprint,
            seat_count=seat_count,
            expiry=expiry,
            license_id=license_id,
            serial=serial,
        )
        token = sign_license_claims(claims.to_dict(), private_key=private_key)
        tokens.append({"customer_id": customer_id, "token": token})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(tokens, indent=2, ensure_ascii=False), encoding="utf-8")
    return tokens


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ferramentas de emissão de licenças offline")
    sub = parser.add_subparsers(dest="command", required=True)

    issue_parser = sub.add_parser("issue", help="Emitir uma única licença")
    issue_parser.add_argument("customer_id", help="Identificador único do cliente")
    issue_parser.add_argument("fingerprint", help="Impressão digital da máquina a autorizar")
    issue_parser.add_argument("--seat-count", type=int, default=1, dest="seat_count")
    issue_parser.add_argument("--expiry", help="Data ISO 8601 de expiração da licença")
    issue_parser.add_argument("--license-id", help="Identificador interno da licença")
    issue_parser.add_argument("--serial", type=int, default=1)
    issue_parser.add_argument("--output", help="Escrever o token para o ficheiro indicado")

    bulk_parser = sub.add_parser("bulk", help="Emitir várias licenças a partir de um CSV")
    bulk_parser.add_argument("input", help="Ficheiro CSV com os clientes")
    bulk_parser.add_argument("output", help="Ficheiro JSON onde os tokens serão guardados")
    bulk_parser.add_argument("--seat-count", type=int, default=1, dest="seat_count")
    bulk_parser.add_argument("--serial", type=int, default=1)

    return parser


def _run_issue(args: argparse.Namespace) -> int:
    private_key = load_private_key()
    token = issue_license_token(
        customer_id=args.customer_id,
        fingerprint=args.fingerprint,
        seat_count=args.seat_count,
        expiry=args.expiry,
        license_id=args.license_id,
        serial=args.serial,
        private_key=private_key,
    )
    if args.output:
        Path(args.output).write_text(token, encoding="utf-8")
    else:
        print(token)
    return 0


def _run_bulk(args: argparse.Namespace) -> int:
    private_key = load_private_key()
    bulk_issue_from_csv(
        args.input,
        output_path=args.output,
        default_seat_count=args.seat_count,
        default_serial=args.serial,
        private_key=private_key,
    )
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "issue":
        return _run_issue(args)
    if args.command == "bulk":
        return _run_bulk(args)
    parser.error("Comando desconhecido")
    return 2  # pragma: no cover - defensive


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
