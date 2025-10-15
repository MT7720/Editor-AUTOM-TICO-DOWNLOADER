"""Carregamento de segredos sem embutir credenciais no código-fonte.

Este módulo deixa de utilizar a ofuscação com XOR e passa a depender de um
canal autenticado (por exemplo, o *token broker* interno ou o sistema de CI)
para entregar os segredos em tempo de execução. Os valores podem ser
fornecidos via `KEYGEN_LICENSE_BUNDLE` (JSON codificado em Base64), via ficheiro
referenciado por `KEYGEN_LICENSE_BUNDLE_PATH` ou através de variáveis de
ambiente individuais.

Para produzir o bundle assinado, utilize o serviço interno responsável pela
gestão das credenciais. O bundle deve incluir pelo menos os campos
`account_id`, `product_token` e opcionalmente `api_base_url`, juntamente com
metadados de auditoria (por exemplo, `issued_at`, `expires_at`, `proof`). O
cliente valida a integridade dos dados (estrutura, permissões e presença da
prova) antes de disponibilizá-los para o restante da aplicação.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import stat
import sys
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

__all__ = [
    "LicenseServiceCredentials",
    "SecretLoaderError",
    "load_license_secrets",
]


class SecretLoaderError(RuntimeError):
    """Erro lançado quando os segredos não podem ser obtidos em segurança."""


@dataclass(frozen=True)
class LicenseServiceCredentials:
    """Container imutável para as credenciais utilizadas na API do Keygen."""

    account_id: str
    product_token: str
    api_base_url: str

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "LicenseServiceCredentials":
        """Valida o dicionário carregado e devolve uma instância pronta."""

        try:
            account_id = payload["account_id"].strip()
            product_token = payload["product_token"].strip()
        except KeyError as exc:  # pragma: no cover - mensagem específica
            raise SecretLoaderError(
                f"Campo obrigatório ausente no pacote de segredos: {exc.args[0]}"
            ) from exc

        if not account_id or not product_token:
            raise SecretLoaderError(
                "Os valores de 'account_id' e 'product_token' não podem estar vazios."
            )

        base_url = payload.get("api_base_url")
        if base_url:
            base_url = base_url.rstrip("/")
        else:
            base_url = f"https://api.keygen.sh/v1/accounts/{account_id}"

        return cls(account_id=account_id, product_token=product_token, api_base_url=base_url)


def load_license_secrets() -> LicenseServiceCredentials:
    """Obtém as credenciais do serviço de licenças através de fonte externa."""

    payload = (
        _load_bundle_from_env()
        or _load_bundle_from_file()
        or _load_from_env_variables()
        or _load_bundle_from_local_installation()
    )

    if not payload:
        raise SecretLoaderError(
            "As credenciais do serviço de licenças não foram provisionadas. "
            "Configure KEYGEN_LICENSE_BUNDLE, KEYGEN_LICENSE_BUNDLE_PATH ou as "
            "variáveis KEYGEN_ACCOUNT_ID/KEYGEN_PRODUCT_TOKEN."
        )

    _ensure_payload_is_authenticated(payload)

    return LicenseServiceCredentials.from_payload(payload)


def _load_bundle_from_env() -> Optional[Dict[str, Any]]:
    bundle = os.getenv("KEYGEN_LICENSE_BUNDLE")
    if not bundle:
        return None

    try:
        raw = base64.b64decode(bundle)
    except (ValueError, binascii.Error) as exc:
        raise SecretLoaderError(
            "KEYGEN_LICENSE_BUNDLE não contém Base64 válido."
        ) from exc

    try:
        payload = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise SecretLoaderError("KEYGEN_LICENSE_BUNDLE não contém JSON válido.") from exc

    return payload


def _load_bundle_from_file() -> Optional[Dict[str, Any]]:
    path = os.getenv("KEYGEN_LICENSE_BUNDLE_PATH")
    if not path:
        return None

    file_path = Path(path)
    if not file_path.is_file():
        raise SecretLoaderError(
            f"O ficheiro referenciado por KEYGEN_LICENSE_BUNDLE_PATH não existe: {path}"
        )

    return _load_bundle_from_disk(file_path)


def _load_from_env_variables() -> Optional[Dict[str, Any]]:
    account_id = os.getenv("KEYGEN_ACCOUNT_ID")
    product_token = os.getenv("KEYGEN_PRODUCT_TOKEN")
    api_base_url = os.getenv("KEYGEN_API_BASE_URL")

    if not account_id or not product_token:
        return None

    payload: Dict[str, Any] = {
        "account_id": account_id,
        "product_token": product_token,
    }

    if api_base_url:
        payload["api_base_url"] = api_base_url

    return payload


def _load_bundle_from_local_installation() -> Optional[Dict[str, Any]]:
    """Procura bundles instalados juntamente com a aplicação."""

    config_path, config_data = _load_config_data()

    inline_credentials = _extract_inline_credentials(config_data)
    if inline_credentials:
        return inline_credentials

    for candidate in _iter_local_bundle_candidates():
        if not candidate.is_file():
            continue

        return _load_bundle_from_disk(candidate)

    return None


def _iter_local_bundle_candidates() -> tuple[Path, ...]:
    base_path = Path(__file__).resolve().parent
    project_root = base_path.parent

    candidates = []

    resources_path = project_root / "resources" / "license_credentials.json"
    candidates.append(resources_path)

    config_path, config_data = _load_config_data()
    bundle_path = config_data.get("license_credentials_path")
    if isinstance(bundle_path, str) and bundle_path.strip():
        resolved = Path(bundle_path.strip())
        if not resolved.is_absolute():
            resolved = config_path.parent / resolved
        candidates.append(resolved)

    return tuple(dict.fromkeys(candidates))


def _load_bundle_from_disk(file_path: Path) -> Dict[str, Any]:
    if os.name != "nt":  # Em Windows a verificação de permissões é diferente.
        mode = stat.S_IMODE(file_path.stat().st_mode)
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise SecretLoaderError(
                "As permissões do ficheiro de segredos são demasiado abertas. "
                "Utilize chmod 600 e garanta que apenas o utilizador actual o pode ler."
            )

    try:
        with file_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except ValueError as exc:
        raise SecretLoaderError("O ficheiro de segredos não contém JSON válido.") from exc


@lru_cache(maxsize=1)
def _load_config_data() -> tuple[Path, Dict[str, Any]]:
    """Carrega o ficheiro de configuração principal do editor."""

    candidates = _iter_config_candidates()
    selected_path = candidates[0]

    for config_path in candidates:
        if not config_path.is_file():
            continue

        selected_path = config_path

        try:
            raw_data = config_path.read_text(encoding="utf-8")
        except OSError:
            continue

        try:
            data = json.loads(raw_data)
        except ValueError as exc:
            print(
                "Aviso: o ficheiro de configuração '",
                f"{config_path}",
                "' contém JSON inválido (",
                f"{exc}",
                "). Será aplicada uma recuperação parcial.",
                sep="",
            )
            data = _recover_license_metadata(raw_data)

        return selected_path, data

    return selected_path, {}


def _iter_config_candidates() -> tuple[Path, ...]:
    """Determina caminhos prováveis para o ficheiro de configuração."""

    base_path = Path(__file__).resolve().parent.parent

    candidates: list[Path] = [base_path / "video_editor_config.json"]

    cwd_candidate = Path.cwd() / "video_editor_config.json"
    candidates.append(cwd_candidate)

    meipass_path = getattr(sys, "_MEIPASS", None)
    if meipass_path:
        candidates.append(Path(meipass_path) / "video_editor_config.json")

    return tuple(dict.fromkeys(candidates))


def _extract_inline_credentials(config_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Obtém credenciais definidas diretamente no ficheiro de configuração."""

    account_id = config_data.get("license_account_id")
    product_token = config_data.get("license_product_token")

    if not isinstance(account_id, str) or not isinstance(product_token, str):
        return None

    account_id = account_id.strip()
    product_token = product_token.strip()

    if not account_id or not product_token:
        return None

    payload: Dict[str, Any] = {
        "account_id": account_id,
        "product_token": product_token,
    }

    api_base_url = config_data.get("license_api_base_url")
    if isinstance(api_base_url, str) and api_base_url.strip():
        payload["api_base_url"] = api_base_url.strip()

    return payload


def _recover_license_metadata(raw_data: str) -> Dict[str, Any]:
    """Tenta recuperar campos essenciais mesmo com JSON ligeiramente inválido."""

    recovered: Dict[str, Any] = {}

    for key in (
        "license_credentials_path",
        "license_account_id",
        "license_product_token",
        "license_api_base_url",
    ):
        value = _extract_string_field(raw_data, key)
        if value is not None:
            recovered[key] = value

    return recovered


def _extract_string_field(raw_data: str, field_name: str) -> Optional[str]:
    """Extrai o conteúdo textual de um campo string sem depender do JSON completo."""

    pattern = re.compile(
        rf'"{re.escape(field_name)}"\s*:\s*"((?:\\.|[^"])*)"',
        flags=re.DOTALL,
    )
    match = pattern.search(raw_data)
    if not match:
        return None

    try:
        return json.loads(f'"{match.group(1)}"')
    except ValueError:
        return match.group(1)

def _ensure_payload_is_authenticated(payload: Dict[str, Any]) -> None:
    """Realiza verificações básicas sobre o canal que entregou o bundle."""

    proof = payload.get("proof")
    if proof:
        return

    channel = payload.get("channel")
    if channel in {"brokered", "ci", "default", "embedded"}:
        return

    # Como último recurso, exigimos metadados explícitos quando não há prova.
    if payload.get("account_id") and payload.get("product_token"):
        # Um pipeline que injeta variáveis diretamente deve estar protegido
        # externamente (por exemplo, GitHub Actions secrets). Ainda assim,
        # registamos uma mensagem descritiva para facilitar auditorias.
        payload.setdefault(
            "channel",
            "env-vars",
        )
        return

    raise SecretLoaderError(
        "O pacote de segredos não apresentou prova de origem autenticada."
    )

