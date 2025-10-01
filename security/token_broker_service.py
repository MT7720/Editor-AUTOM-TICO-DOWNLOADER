"""Serviço simples de corretagem de tokens para a aplicação desktop.

Este módulo implementa um pequeno endpoint HTTP responsável por trocar
chaves de licença válidas por credenciais temporárias, reduzindo a
necessidade de distribuir o token de produto da API com os clientes.

O serviço valida a chave junto ao Keygen e, em seguida, solicita um
token delegado com o escopo mínimo necessário para ativar máquinas. O
token é devolvido ao cliente juntamente com a respectiva data de
expiração, permitindo que o `license_checker.py` o armazene em cache
até perto do término.

O servidor pode ser executado com:

```
python -m security.token_broker_service
```

As seguintes variáveis de ambiente devem estar configuradas:

```
KEYGEN_ACCOUNT_ID            Identificador da conta no Keygen.
KEYGEN_PRODUCT_TOKEN         Token de produto de longa duração (mantido no backend).
TOKEN_BROKER_SHARED_SECRET   Segredo partilhado usado para autenticar clientes.
TOKEN_BROKER_TOKEN_TTL       (Opcional) Validade em segundos do token delegado.
TOKEN_BROKER_SCOPE           (Opcional) Lista separada por espaços com os escopos do token.
KEYGEN_API_BASE_URL          (Opcional) Base URL da API do Keygen (por defeito usa a conta acima).
```
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Tuple

import requests

logger = logging.getLogger(__name__)


ACCOUNT_ID = os.getenv("KEYGEN_ACCOUNT_ID", "9798e344-f107-4cfd-bc83-af9b8e75d352")
API_BASE_URL = os.getenv(
    "KEYGEN_API_BASE_URL", f"https://api.keygen.sh/v1/accounts/{ACCOUNT_ID}"
)
PRODUCT_TOKEN_ENV_VAR = "KEYGEN_PRODUCT_TOKEN"
BROKER_SHARED_SECRET_ENV_VAR = "TOKEN_BROKER_SHARED_SECRET"
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_BROKER_TOKEN_TTL", "300"))
DEFAULT_SCOPE = os.getenv(
    "TOKEN_BROKER_SCOPE", "machines:create machines:read licenses:read"
).split()


class BrokerError(RuntimeError):
    """Erro recuperável ocorrido durante a emissão da credencial delegada."""


def _require_product_token() -> str:
    token = os.getenv(PRODUCT_TOKEN_ENV_VAR)
    if not token:
        raise BrokerError(
            "KEYGEN_PRODUCT_TOKEN não está definido para o serviço de corretagem."
        )
    return token


def _keygen_headers() -> Dict[str, str]:
    token = _require_product_token()
    return {
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
        "Authorization": f"Bearer {token}",
    }


def _validate_license_key(license_key: str) -> str:
    payload = {"meta": {"key": license_key}}
    response = requests.post(
        f"{API_BASE_URL}/licenses/actions/validate-key",
        json=payload,
        headers=_keygen_headers(),
        timeout=10,
    )
    response.raise_for_status()
    body = response.json()
    if not body.get("meta", {}).get("valid"):
        raise BrokerError(body.get("meta", {}).get("detail", "Chave de licença inválida."))
    try:
        return body["data"]["id"]
    except KeyError as exc:  # pragma: no cover - defensivo
        raise BrokerError("Resposta inesperada do Keygen ao validar a chave.") from exc


def _issue_scoped_token(license_id: str) -> Tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=TOKEN_TTL_SECONDS)
    payload = {
        "data": {
            "type": "tokens",
            "attributes": {
                "expiry": expires_at.isoformat(),
                "scope": DEFAULT_SCOPE,
            },
            "relationships": {
                "license": {"data": {"type": "licenses", "id": license_id}}
            },
        }
    }
    response = requests.post(
        f"{API_BASE_URL}/tokens",
        json=payload,
        headers=_keygen_headers(),
        timeout=10,
    )
    response.raise_for_status()
    body = response.json()
    try:
        token = body["data"]["attributes"]["token"]
    except KeyError as exc:  # pragma: no cover - defensivo
        raise BrokerError("Resposta inesperada ao gerar token delegado.") from exc
    return token, expires_at


def _issue_delegated_credential(license_key: str) -> Tuple[str, datetime]:
    license_id = _validate_license_key(license_key)
    return _issue_scoped_token(license_id)


def _is_authorized(headers: Dict[str, str]) -> bool:
    expected_secret = os.getenv(BROKER_SHARED_SECRET_ENV_VAR)
    if not expected_secret:
        return True
    provided = headers.get("X-Broker-Secret", "")
    return provided and secrets_compare(provided, expected_secret)


def secrets_compare(value: str, expected: str) -> bool:
    return hmac.compare_digest(value.encode("utf-8"), expected.encode("utf-8"))


class TokenRequestHandler(BaseHTTPRequestHandler):
    server_version = "TokenBroker/1.0"

    def _write_response(self, status: HTTPStatus, payload: Dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - método requerido pelo BaseHTTPRequestHandler
        if self.path.rstrip("/") != "/v1/delegated-credentials":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        if not _is_authorized(self.headers):
            self._write_response(HTTPStatus.FORBIDDEN, {"error": "unauthorized"})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except json.JSONDecodeError:
            self._write_response(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
            return

        license_key = (payload.get("licenseKey") or "").strip()
        if not license_key:
            self._write_response(HTTPStatus.BAD_REQUEST, {"error": "license_key_required"})
            return

        try:
            token, expires_at = _issue_delegated_credential(license_key)
        except BrokerError as exc:
            logger.warning("Falha ao emitir credencial delegada: %s", exc)
            self._write_response(HTTPStatus.FORBIDDEN, {"error": str(exc)})
            return
        except requests.exceptions.RequestException as exc:
            logger.exception("Erro ao contactar o Keygen: %s", exc)
            self._write_response(HTTPStatus.BAD_GATEWAY, {"error": "upstream_error"})
            return

        response_payload = {
            "token": token,
            "expiresAt": expires_at.isoformat(),
            "scope": DEFAULT_SCOPE,
        }
        self._write_response(HTTPStatus.OK, response_payload)

    def log_message(self, format: str, *args) -> None:  # noqa: A003 - assinatura herdada
        logger.info("%s - - %s", self.address_string(), format % args)


def run_server(host: str = "0.0.0.0", port: int = 8080) -> None:
    logging.basicConfig(level=logging.INFO)
    with HTTPServer((host, port), TokenRequestHandler) as httpd:
        logger.info("Token broker a escutar em %s:%s", host, port)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:  # pragma: no cover - interativo
            logger.info("Encerrando o token broker.")


if __name__ == "__main__":  # pragma: no cover - apenas execução manual
    run_server()

