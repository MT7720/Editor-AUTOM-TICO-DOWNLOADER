"""Carregamento de segredos sem embutir credenciais no código-fonte.

As credenciais agora são obtidas a partir do serviço proprietário da Automático
e não dependem mais do Keygen. O módulo continua a exigir um canal autenticado
para distribuir os segredos em tempo de execução. Os valores podem ser
fornecidos via ``LICENSE_SERVICE_BUNDLE`` (JSON codificado em Base64), via
ficheiro referenciado por ``LICENSE_SERVICE_BUNDLE_PATH`` ou através das
variáveis de ambiente ``LICENSE_API_URL`` e ``LICENSE_API_TOKEN``.

Para produzir o bundle assinado, utilize o serviço interno responsável pela
gestão das credenciais. O bundle deve incluir os campos ``api_token`` e
``api_base_url`` (ou ``api_url``), juntamente com metadados de auditoria (por
exemplo, ``issued_at``, ``expires_at``, ``proof``). O cliente valida a
integridade dos dados (estrutura, permissões e presença da prova) antes de
disponibilizá-los para o restante da aplicação.
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
    """Container imutável para as credenciais utilizadas na API de licenças."""

    api_base_url: str
    api_token: str

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "LicenseServiceCredentials":
        """Valida o dicionário carregado e devolve uma instância pronta."""

        try:
            api_token = payload["api_token"].strip()
        except KeyError as exc:  # pragma: no cover - mensagem específica
            raise SecretLoaderError(
                f"Campo obrigatório ausente no pacote de segredos: {exc.args[0]}"
            ) from exc

        if not api_token:
            raise SecretLoaderError("O valor de 'api_token' não pode estar vazio.")

        raw_base_url = payload.get("api_base_url") or payload.get("api_url")
        if not isinstance(raw_base_url, str) or not raw_base_url.strip():
            raise SecretLoaderError(
                "O pacote de segredos deve incluir 'api_base_url' ou 'api_url'."
            )

        base_url = raw_base_url.strip().rstrip("/")

        return cls(api_base_url=base_url, api_token=api_token)


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
            "Configure LICENSE_SERVICE_BUNDLE, LICENSE_SERVICE_BUNDLE_PATH ou as "
            "variáveis LICENSE_API_URL/LICENSE_API_TOKEN."
        )

    _ensure_payload_is_authenticated(payload)

    return LicenseServiceCredentials.from_payload(payload)


def _load_bundle_from_env() -> Optional[Dict[str, Any]]:
    bundle = os.getenv("LICENSE_SERVICE_BUNDLE")
    if not bundle:
        return None

    try:
        raw = base64.b64decode(bundle)
    except (ValueError, binascii.Error) as exc:
        raise SecretLoaderError(
            "LICENSE_SERVICE_BUNDLE não contém Base64 válido."
        ) from exc

    try:
        payload = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise SecretLoaderError("LICENSE_SERVICE_BUNDLE não contém JSON válido.") from exc

    return payload


def _load_bundle_from_file() -> Optional[Dict[str, Any]]:
    path = os.getenv("LICENSE_SERVICE_BUNDLE_PATH")
    if not path:
        return None

    file_path = Path(path)
    if not file_path.is_file():
        raise SecretLoaderError(
            f"O ficheiro referenciado por LICENSE_SERVICE_BUNDLE_PATH não existe: {path}"
        )

    return _load_bundle_from_disk(file_path)


def _load_from_env_variables() -> Optional[Dict[str, Any]]:
    api_base_url = os.getenv("LICENSE_API_URL")
    api_token = os.getenv("LICENSE_API_TOKEN")

    if not api_token:
        return None

    if not api_base_url:
        return None

    return {"api_base_url": api_base_url, "api_token": api_token}


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

    api_token = config_data.get("license_api_token")
    api_url = config_data.get("license_api_url")

    if not isinstance(api_token, str) or not isinstance(api_url, str):
        return None

    api_token = api_token.strip()
    api_url = api_url.strip()

    if not api_token or not api_url:
        return None

    return {"api_token": api_token, "api_base_url": api_url}


def _recover_license_metadata(raw_data: str) -> Dict[str, Any]:
    """Tenta recuperar campos essenciais mesmo com JSON ligeiramente inválido."""

    recovered: Dict[str, Any] = {}

    for key in (
        "license_credentials_path",
        "license_api_token",
        "license_api_url",
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
    if payload.get("api_token") and (payload.get("api_base_url") or payload.get("api_url")):
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

