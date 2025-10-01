"""Guarda de segurança executado antes da inicialização da GUI."""
from __future__ import annotations

import base64
import binascii
import ctypes
import hashlib
import hmac
import inspect
import json
import logging
import os
import platform
import sys
from pathlib import Path
from typing import Dict, List, Optional, cast

LOG_NAME = "security.runtime_guard"
LOG_FILE_NAME = "runtime_guard.log"
_MANIFEST_FILENAME = "runtime_manifest.json"
_HMAC_KEY_ENV_VAR = "RUNTIME_GUARD_HMAC_KEY"


class SecurityViolation(RuntimeError):
    """Erro lançado quando uma violação de segurança é detectada."""


_logger: Optional[logging.Logger] = None
_manifest_cache: Optional[Dict[str, object]] = None
_HMAC_KEY_UNINITIALIZED: object = object()
_hmac_key_cache: object = _HMAC_KEY_UNINITIALIZED


def _get_logger() -> logging.Logger:
    global _logger
    if _logger:
        return _logger

    logger = logging.getLogger(LOG_NAME)
    logger.setLevel(logging.INFO)

    log_path = _resolve_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(log_path, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(handler)
    try:
        os.chmod(log_path, 0o600)
    except OSError:
        pass

    _logger = logger
    return logger


def _resolve_log_path() -> Path:
    base = _get_app_base_path()
    log_dir = base / "logs"
    return log_dir / LOG_FILE_NAME


def _get_app_base_path() -> Path:
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS)  # type: ignore[attr-defined]
        return Path(os.path.dirname(sys.executable))
    return Path(__file__).resolve().parent.parent


def _manifest_path() -> Path:
    return Path(__file__).with_name(_MANIFEST_FILENAME)


def _load_manifest() -> Dict[str, object]:
    global _manifest_cache
    if _manifest_cache is None:
        manifest_path = _manifest_path()
        with manifest_path.open("r", encoding="utf-8") as file_handle:
            _manifest_cache = cast(Dict[str, object], json.load(file_handle))
    return _manifest_cache


MANIFEST: Dict[str, object] = _load_manifest()


def _load_hmac_key() -> Optional[bytes]:
    global _hmac_key_cache
    if _hmac_key_cache is not _HMAC_KEY_UNINITIALIZED:
        return cast(Optional[bytes], _hmac_key_cache)

    raw_value = os.getenv(_HMAC_KEY_ENV_VAR)
    if not raw_value:
        _get_logger().error(
            "Variável de ambiente %s ausente; assinaturas do manifesto não podem ser validadas.",
            _HMAC_KEY_ENV_VAR,
        )
        _hmac_key_cache = None
        return None

    try:
        key = base64.b64decode(raw_value, validate=True)
    except (binascii.Error, ValueError) as exc:
        _get_logger().error(
            "Falha ao decodificar a chave HMAC a partir de %s: %s", _HMAC_KEY_ENV_VAR, exc
        )
        _hmac_key_cache = None
        return None

    if not key:
        _get_logger().error("Chave HMAC decodificada é vazia; verifique a configuração do ambiente")
        _hmac_key_cache = None
        return None

    _hmac_key_cache = key
    return key


def _calculate_file_hash(path: Path, algorithm: str, *, normalize_newlines: bool = False) -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(65536), b""):
            if normalize_newlines:
                chunk = chunk.replace(b"\r\n", b"\n")
            h.update(chunk)
    return h.hexdigest()


def _verify_signature(expected_hash: str, signature: str) -> bool:
    key = _load_hmac_key()
    if key is None:
        return False
    expected_signature = hmac.new(key, expected_hash.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_signature, signature)


def _resolve_resource_path(resource: Dict[str, str]) -> Path:
    rel_path = resource["path"]
    base = _get_app_base_path()
    return base / rel_path


def _collect_resource_violations(manifest: Dict[str, object]) -> List[str]:
    # Quando executado em modo desenvolvimento (sem estar empacotado via PyInstaller),
    # os recursos são carregados diretamente do diretório do projeto. Esse fluxo está
    # sujeito a modificações legítimas durante o desenvolvimento e, portanto,
    # ignoramos a validação de hashes nesses casos, mantendo-a apenas para builds
    # empacotados.
    if not getattr(sys, "frozen", False):
        return []

    key = _load_hmac_key()
    if key is None:
        return [
            "Chave de assinatura do manifesto ausente ou inválida; não é possível validar recursos",
        ]

    algorithm = manifest.get("algorithm", "sha256")
    resources: Dict[str, Dict[str, str]] = manifest.get("resources", {})  # type: ignore[assignment]
    violations: List[str] = []

    for name, resource in resources.items():
        path = _resolve_resource_path(resource)
        expected_hash = resource.get("hash")
        signature = resource.get("signature")
        if not expected_hash or not signature:
            violations.append(f"Assinatura ausente para recurso crítico '{name}'")
            continue
        if not _verify_signature(expected_hash, signature):
            violations.append(f"Assinatura inválida para recurso '{name}'")
            continue
        if not path.exists():
            violations.append(f"Recurso esperado não encontrado: {path}")
            continue
        normalize_newlines = bool(resource.get("normalize_newlines"))
        calculated_hash = _calculate_file_hash(path, algorithm, normalize_newlines=normalize_newlines)
        if not hmac.compare_digest(calculated_hash, expected_hash):
            violations.append(
                f"Hash divergente para '{name}'. Esperado={expected_hash} Obtido={calculated_hash}"
            )
    return violations


def _select_executable_entry(executables_manifest: Dict[str, Dict[str, str]]) -> Optional[Dict[str, str]]:
    architecture, _ = platform.architecture()
    machine = platform.machine().lower()
    candidates: List[str] = []

    if sys.platform.startswith("win"):
        if architecture.startswith("32"):
            candidates.extend(["win32", machine])
        else:
            candidates.extend(["win_amd64", machine])
    elif sys.platform == "darwin":
        candidates.append("darwin")
    else:
        if architecture.startswith("32"):
            candidates.append("linux32")
        else:
            candidates.append("linux64")
        candidates.append(machine)

    candidates.append("default")

    for key in candidates:
        if key in executables_manifest:
            return executables_manifest[key]
    return None


def _collect_executable_violations(manifest: Dict[str, object]) -> List[str]:
    executables: Dict[str, Dict[str, str]] = manifest.get("executables", {})  # type: ignore[assignment]
    if not executables:
        return []

    # Quando o aplicativo está sendo executado diretamente do código-fonte (por exemplo,
    # ``python main.py``), ``sys.executable`` aponta para o interpretador Python
    # instalado na máquina do usuário. O manifesto, porém, contém apenas os hashes
    # calculados para os executáveis empacotados (PyInstaller). Comparar o hash do
    # interpretador local com esses valores faria a verificação falhar
    # indevidamente, impedindo o uso em modo desenvolvimento. Nesse cenário,
    # simplesmente pulamos a validação do executável.
    if not getattr(sys, "frozen", False):
        return []

    if _load_hmac_key() is None:
        return [
            "Chave de assinatura do manifesto ausente ou inválida; não é possível validar o executável",
        ]

    entry = _select_executable_entry(executables)
    if not entry:
        return ["Nenhuma referência de hash disponível para o executável atual"]

    expected_hash = entry.get("hash")
    signature = entry.get("signature")
    if not expected_hash or not signature:
        return ["Manifesto do executável sem hash ou assinatura"]
    if not _verify_signature(expected_hash, signature):
        return ["Assinatura inválida para hash do executável"]

    executable_path = Path(sys.executable)
    if not executable_path.exists():
        return [f"Executável atual não encontrado: {executable_path}"]

    algorithm = manifest.get("algorithm", "sha256")
    calculated_hash = _calculate_file_hash(executable_path, algorithm)  # type: ignore[arg-type]
    allowed = {expected_hash}

    env_hashes = os.getenv("RUNTIME_GUARD_ALLOWED_EXEC_HASHES")
    if env_hashes:
        allowed.update(hash_value.strip() for hash_value in env_hashes.split(",") if hash_value.strip())

    if calculated_hash not in allowed:
        return [
            "Hash do executável divergente. A aplicação pode ter sido modificada ou corrompida.",
        ]
    return []


def _collect_debugger_violations() -> List[str]:
    violations: List[str] = []
    trace = sys.gettrace()
    if trace is not None:
        violations.append("Função de trace ativa detectada (possível depurador)")

    for mod_name in ("pydevd", "pydevd_pycharm", "pydevd_file_utils"):
        if mod_name in sys.modules:
            violations.append(f"Módulo de depuração detectado: {mod_name}")

    if sys.platform.startswith("win"):
        try:
            if ctypes.windll.kernel32.IsDebuggerPresent():  # type: ignore[attr-defined]
                violations.append("Debugger nativo detectado (IsDebuggerPresent)")
        except Exception as exc:  # pragma: no cover - ambiente não Windows
            _get_logger().warning("Falha ao consultar IsDebuggerPresent: %s", exc)

    return violations


def _collect_instrumentation_violations() -> List[str]:
    violations: List[str] = []
    gettrace = getattr(sys, "gettrace", None)
    if gettrace is None:
        violations.append("sys.gettrace não disponível; ambiente pode estar instrumentado")
    else:
        module_name = getattr(gettrace, "__module__", "")
        qualname = getattr(gettrace, "__qualname__", getattr(gettrace, "__name__", ""))
        if module_name not in {"builtins", "sys"} and not inspect.isbuiltin(gettrace):
            violations.append(f"Implementação de gettrace substituída por {module_name}.{qualname}")

    if getattr(sys, "getprofile", lambda: None)() is not None:
        violations.append("Função de profile ativa (possível instrumentação)")

    return violations


def enforce_runtime_safety() -> None:
    """Executa todas as verificações e interrompe o programa em caso de violação."""
    manifest = _load_manifest()
    violations: List[str] = []
    violations.extend(_collect_resource_violations(manifest))
    violations.extend(_collect_executable_violations(manifest))
    violations.extend(_collect_debugger_violations())
    violations.extend(_collect_instrumentation_violations())

    logger = _get_logger()
    if violations:
        for item in violations:
            logger.error("Violação de segurança: %s", item)
        raise SecurityViolation("; ".join(violations))
    logger.info("Verificações de segurança concluídas com sucesso")
