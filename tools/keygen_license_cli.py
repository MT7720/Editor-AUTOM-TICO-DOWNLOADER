"""Utilities for managing Keygen licenses for the Editor Automático."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

import requests

from security.license_authority import issue_license_token

DEFAULT_ACCOUNT_ID = "9798e344-f107-4cfd-bc83-af9b8e75d352"
DEFAULT_BASE_URL_TEMPLATE = "https://api.keygen.sh/v1/accounts/{account_id}"

JSON_API_HEADERS = {
    "Accept": "application/vnd.api+json",
    "Content-Type": "application/vnd.api+json",
}


class KeygenError(RuntimeError):
    """Raised when the Keygen API returns an error response."""


class KeygenClient:
    """Minimal JSON:API client used to call Keygen endpoints."""

    def __init__(
        self,
        product_token: str,
        account_id: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 15,
    ) -> None:
        if not product_token:
            raise KeygenError(
                "É necessário definir KEYGEN_PRODUCT_TOKEN para contactar a API do Keygen."
            )
        self.account_id = account_id or os.getenv("KEYGEN_ACCOUNT_ID") or DEFAULT_ACCOUNT_ID
        self.base_url = base_url or os.getenv(
            "KEYGEN_API_BASE_URL", DEFAULT_BASE_URL_TEMPLATE.format(account_id=self.account_id)
        )
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(JSON_API_HEADERS)
        self.session.headers["Authorization"] = f"Bearer {product_token}"

    def _request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        try:
            payload = response.json()
        except ValueError:
            payload = None

        if not response.ok:
            message = self._extract_error(payload) if payload else response.text
            raise KeygenError(f"Erro do Keygen ({response.status_code}): {message}")

        return payload or {}

    @staticmethod
    def _extract_error(payload: Optional[Dict[str, Any]]) -> str:
        if not payload:
            return "Resposta vazia do Keygen"
        errors = payload.get("errors")
        if not isinstance(errors, list):
            return json.dumps(payload)
        details: Iterable[str] = (
            str(err.get("detail") or err.get("title") or err) for err in errors
        )
        return "; ".join(details)

    def list_policies(self) -> Iterable[Dict[str, Any]]:
        payload = self._request("GET", "/policies")
        return payload.get("data", [])

    def create_license(
        self,
        policy_id: str,
        name: str,
        email: Optional[str] = None,
        expiry: Optional[str] = None,
        max_machines: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        attributes: Dict[str, Any] = {"name": name}
        if email:
            attributes.setdefault("metadata", {})["email"] = email
        if metadata:
            attributes.setdefault("metadata", {}).update(metadata)
        if expiry:
            attributes["expiry"] = expiry
        if max_machines is not None:
            attributes["maxMachines"] = max_machines

        data: Dict[str, Any] = {
            "data": {
                "type": "licenses",
                "attributes": attributes,
                "relationships": {
                    "policy": {"data": {"type": "policies", "id": policy_id}}
                },
            }
        }

        if user_id:
            data["data"]["relationships"]["user"] = {
                "data": {"type": "users", "id": user_id}
            }

        payload = self._request("POST", "/licenses", json=data)
        return payload.get("data", {})

    def retrieve_license(self, license_id: str) -> Dict[str, Any]:
        payload = self._request("GET", f"/licenses/{license_id}")
        return payload.get("data", {})


def _parse_metadata(values: Iterable[str]) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    for item in values:
        if "=" not in item:
            raise argparse.ArgumentTypeError(
                f"Metadado inválido '{item}'. Use o formato chave=valor."
            )
        key, value = item.split("=", 1)
        metadata[key] = value
    return metadata


def _print_policies(_: argparse.Namespace, client: KeygenClient) -> None:
    policies = list(client.list_policies())
    if not policies:
        print("Nenhuma política foi encontrada para a conta informada.")
        return

    print("Políticas disponíveis:")
    for policy in policies:
        attributes = policy.get("attributes", {})
        print("- ID: {id}\n  Nome: {name}\n  Licenças máximas: {max_machines}".format(
            id=policy.get("id"),
            name=attributes.get("name", "(sem nome)"),
            max_machines=attributes.get("maxMachines", "ilimitado"),
        ))
        if attributes.get("description"):
            print(f"  Descrição: {attributes['description']}")
        print()


def _handle_create_license(args: argparse.Namespace, client: KeygenClient) -> None:
    metadata = _parse_metadata(args.metadata or []) if args.metadata else None
    license_data = client.create_license(
        policy_id=args.policy,
        name=args.name,
        email=args.email,
        expiry=args.expiry,
        max_machines=args.max_machines,
        metadata=metadata,
        user_id=args.user,
    )

    attributes = license_data.get("attributes", {})
    key = attributes.get("key") or license_data.get("id")
    print("Licença criada com sucesso!")
    print(json.dumps({"id": license_data.get("id"), "key": key, "attributes": attributes}, indent=2))


def _handle_issue_token(args: argparse.Namespace, client: KeygenClient) -> None:
    license_data = client.retrieve_license(args.license)
    if not license_data:
        raise KeygenError(f"Licença {args.license} não foi encontrada.")

    attributes = license_data.get("attributes", {})

    expiry_iso = args.expiry or attributes.get("expiry")
    if not expiry_iso:
        raise KeygenError(
            "A licença não possui data de expiração definida. Informe --expiry com um timestamp ISO 8601."
        )

    try:
        expiry_dt = datetime.fromisoformat(expiry_iso.replace("Z", "+00:00"))
    except ValueError as exc:
        raise KeygenError("Formato inválido para a data de expiração. Utilize ISO 8601.") from exc
    if expiry_dt.tzinfo is None:
        expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)

    seats = args.seats
    if seats is None:
        seats = attributes.get("maxMachines") or attributes.get("maxSeats")
    if seats is None:
        seats = 1

    token = issue_license_token(
        customer_id=license_data.get("id", ""),
        fingerprint=args.fingerprint,
        expiry=expiry_dt,
        seats=int(seats),
        serial=args.serial,
    )

    payload = {
        "license": license_data.get("id"),
        "fingerprint": args.fingerprint,
        "token": token,
        "expiry": expiry_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "seats": seats,
        "serial": args.serial or "(gerado automaticamente)",
    }
    print(json.dumps(payload, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Ferramentas auxiliares para integrar o Keygen com o processo de licenciamento do Editor Automático."
        )
    )
    parser.add_argument(
        "--product-token",
        default=os.getenv("KEYGEN_PRODUCT_TOKEN"),
        help="Token de produto do Keygen (também pode ser definido em KEYGEN_PRODUCT_TOKEN)",
    )
    parser.add_argument(
        "--account-id",
        default=os.getenv("KEYGEN_ACCOUNT_ID", DEFAULT_ACCOUNT_ID),
        help="Identificador da conta no Keygen",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("KEYGEN_API_BASE_URL"),
        help="URL base da API do Keygen (opcional)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    policies_parser = subparsers.add_parser("policies", help="Lista as políticas disponíveis")
    policies_parser.set_defaults(handler=_print_policies)

    create_parser = subparsers.add_parser("create-license", help="Cria uma nova licença no Keygen")
    create_parser.add_argument("--policy", required=True, help="Identificador da política de licenciamento")
    create_parser.add_argument("--name", required=True, help="Nome do titular da licença")
    create_parser.add_argument("--email", help="Email do cliente (guardado em metadata)")
    create_parser.add_argument("--expiry", help="Data de expiração ISO 8601 (ex: 2025-12-31T23:59:59Z)")
    create_parser.add_argument("--max-machines", type=int, help="Número máximo de máquinas autorizadas")
    create_parser.add_argument(
        "--metadata",
        nargs="*",
        help="Entradas adicionais de metadata no formato chave=valor",
    )
    create_parser.add_argument("--user", help="Associar a licença a um utilizador existente")
    create_parser.set_defaults(handler=_handle_create_license)

    token_parser = subparsers.add_parser(
        "issue-token",
        help="Emite um token offline compatível com o cliente a partir de uma licença Keygen",
    )
    token_parser.add_argument("--license", required=True, help="Identificador da licença no Keygen")
    token_parser.add_argument(
        "--fingerprint", required=True, help="Impressão digital da máquina que receberá o token"
    )
    token_parser.add_argument(
        "--expiry",
        help="Data de expiração ISO 8601. Usa a expiração da licença se omitido.",
    )
    token_parser.add_argument(
        "--seats",
        type=int,
        help="Número de assentos incluídos no token (padrão: maxMachines da licença)",
    )
    token_parser.add_argument(
        "--serial",
        help="Número de série opcional a utilizar. Se omitido será gerado automaticamente.",
    )
    token_parser.set_defaults(handler=_handle_issue_token)

    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        client = KeygenClient(
            product_token=args.product_token,
            account_id=args.account_id,
            base_url=args.base_url,
        )
    except KeygenError as exc:
        parser.error(str(exc))
        return 2
    except Exception as exc:  # pragma: no cover - defensive
        parser.error(f"Falha ao inicializar o cliente Keygen: {exc}")
        return 2

    handler = getattr(args, "handler", None)
    if not handler:
        parser.error("Nenhum comando foi seleccionado.")
        return 2

    try:
        handler(args, client)  # type: ignore[arg-type]
    except KeygenError as exc:
        parser.error(str(exc))
        return 1
    except requests.RequestException as exc:
        parser.error(f"Erro de rede ao contactar o Keygen: {exc}")
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry-point
    sys.exit(main())
