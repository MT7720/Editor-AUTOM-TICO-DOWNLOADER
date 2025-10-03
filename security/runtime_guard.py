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
import threading
import random
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
    return Path(__file__).resolve().parent / _MANIFEST_FILENAME

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
        _get_logger().error("Variável de ambiente %s ausente.", _HMAC_KEY_ENV_VAR)
        _hmac_key_cache = None
        return None
    try:
        key = base64.b64decode(raw_value, validate=True)
    except (binascii.Error, ValueError) as exc:
        _get_logger().error("Falha ao decodificar a chave HMAC: %s", exc)
        _hmac_key_cache = None
        return None
    if not key:
        _get_logger().error("Chave HMAC decodificada é vazia.")
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
    if not getattr(sys, "frozen", False): return []
    if _load_hmac_key() is None: return ["Chave de assinatura ausente."]
    
    violations: List[str] = []
    algorithm = manifest.get("algorithm", "sha256")
    resources: Dict[str, Dict[str, str]] = manifest.get("resources", {})  # type: ignore[assignment]
    for name, resource in resources.items():
        path = _resolve_resource_path(resource)
        expected_hash, signature = resource.get("hash"), resource.get("signature")
        if not (expected_hash and signature and _verify_signature(expected_hash, signature)):
            violations.append(f"Assinatura inválida para recurso '{name}'")
            continue
        if not path.exists():
            violations.append(f"Recurso não encontrado: {path}")
            continue
        normalize = bool(resource.get("normalize_newlines"))
        calculated_hash = _calculate_file_hash(path, algorithm, normalize_newlines=normalize)
        if not hmac.compare_digest(calculated_hash, expected_hash):
            violations.append(f"Hash divergente para '{name}'")
    return violations

def _select_executable_entry(executables: Dict[str, Dict[str, str]]) -> Optional[Dict[str, str]]:
    arch, _ = platform.architecture()
    plat = sys.platform
    key = "default"
    if plat.startswith("win"): key = "win_amd64" if arch.startswith("64") else "win32"
    elif plat == "darwin": key = "darwin"
    return executables.get(key, executables.get("default"))

def _collect_executable_violations(manifest: Dict[str, object]) -> List[str]:
    if not getattr(sys, "frozen", False): return []
    if _load_hmac_key() is None: return ["Chave de assinatura ausente."]

    executables: Dict[str, Dict[str, str]] = manifest.get("executables", {}) # type: ignore[assignment]
    entry = _select_executable_entry(executables)
    if not entry: return ["Nenhuma referência de hash para o executável atual."]
    
    expected_hash, signature = entry.get("hash"), entry.get("signature")
    if not (expected_hash and signature and _verify_signature(expected_hash, signature)):
        return ["Assinatura inválida para hash do executável."]
        
    calc_hash = _calculate_file_hash(Path(sys.executable), manifest.get("algorithm", "sha256"))
    if not hmac.compare_digest(calc_hash, expected_hash):
        return ["Hash do executável divergente. Aplicação modificada."]
    return []

def _collect_debugger_violations() -> List[str]:
    violations: List[str] = []
    if sys.gettrace() is not None:
        violations.append("Função de trace ativa (possível depurador)")
    if "pydevd" in sys.modules:
        violations.append("Módulo de depuração 'pydevd' detectado")
    if sys.platform.startswith("win") and ctypes.windll.kernel32.IsDebuggerPresent():
        violations.append("Debugger nativo detectado (IsDebuggerPresent)")
    return violations

def _collect_instrumentation_violations() -> List[str]:
    violations: List[str] = []
    gettrace = getattr(sys, "gettrace", None)
    if gettrace and getattr(gettrace, "__module__", "") not in {"builtins", "sys"}:
        violations.append("sys.gettrace substituído por implementação externa")
    return violations

def _perform_all_checks():
    """Executa todas as verificações e retorna uma lista de violações."""
    manifest = _load_manifest()
    violations: List[str] = []
    violations.extend(_collect_resource_violations(manifest))
    violations.extend(_collect_executable_violations(manifest))
    violations.extend(_collect_debugger_violations())
    violations.extend(_collect_instrumentation_violations())
    return violations

def enforce_runtime_safety():
    """Executa verificações na inicialização. Lança exceção em caso de falha."""
    violations = _perform_all_checks()
    logger = _get_logger()
    if violations:
        for item in violations:
            logger.error("Violação de segurança: %s", item)
        # Encerra abruptamente em vez de lançar exceção para dificultar a captura
        os._exit(1)
    logger.info("Verificações de segurança iniciais concluídas com sucesso")

def _scheduled_check():
    """Função executada periodicamente para revalidar a segurança."""
    logger = _get_logger()
    logger.info("Executando verificação de segurança agendada...")
    violations = _perform_all_checks()
    if violations:
        logger.error("Violação detectada durante verificação agendada. Encerrando.")
        for item in violations:
            logger.error("Violação: %s", item)
        os._exit(1) # Encerramento imediato
    
    # Reagenda a próxima verificação em um intervalo aleatório
    schedule_integrity_check()

def schedule_integrity_check():
    """Agenda a próxima verificação de integridade em um intervalo aleatório."""
    # Intervalo entre 5 e 15 minutos (300 a 900 segundos)
    delay = random.uniform(300, 900)
    _get_logger().info(f"Próxima verificação de segurança agendada em {delay:.2f} segundos.")
    timer = threading.Timer(delay, _scheduled_check)
    timer.daemon = True
    timer.start()
