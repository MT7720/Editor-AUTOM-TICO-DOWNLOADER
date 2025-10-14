"""Guarda de segurança executado antes da inicialização da GUI."""
from __future__ import annotations

import ctypes
import hashlib
import hmac
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

INTEGRITY_CHECK_INTERVAL_SECONDS = 300

# --- CHAVE DE SEGURANÇA EMBUTIDA ---
_XOR_KEY = b"uma-chave-simples-para-ofuscar-a-outra"
_ENCODED_HMAC_KEY = b'=\\H\x07\r\t[\x10\x17X\x1c\x04\x0e\x01\x10\rW\x02\x05\t\x0b\x06\x11X\r\x1c\x01\x1b\x02\x04\x1a\x11W\x0e\t\x03\x01\x1a\x17\rX\x06\t\x02\x01\x17\x04W\x1e\x1d\x1a'

def _xor_cipher(data: bytes, key: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(data, (key * (len(data) // len(key) + 1))[:len(data)]))

def _get_embedded_hmac_key() -> bytes:
    return _xor_cipher(_ENCODED_HMAC_KEY, _XOR_KEY)

class SecurityViolation(RuntimeError):
    """Erro levantado quando uma violação de segurança é detectada."""

_logger: Optional[logging.Logger] = None
_manifest_cache: Optional[Dict[str, object]] = None
_HMAC_KEY_UNINITIALIZED: object = object()
_hmac_key_cache: object = _HMAC_KEY_UNINITIALIZED

_integrity_lock = threading.Lock()
_integrity_timer: Optional[threading.Timer] = None
_integrity_scheduler_started = False

# --- FUNÇÃO CORRIGIDA PARA ENCONTRAR O CAMINHO BASE DOS LOGS ---
def _get_external_base_path() -> Path:
    """Retorna o caminho base para arquivos externos como logs, garantindo que fiquem ao lado do .exe."""
    if getattr(sys, "frozen", False):
        # Quando compilado (.exe), o caminho correto é o diretório do executável.
        return Path(os.path.dirname(sys.executable))
    # Em modo de desenvolvimento, é a raiz do projeto.
    return Path(__file__).resolve().parent.parent

def _resolve_log_path() -> Path:
    base = _get_external_base_path() # Usa a nova função
    log_dir = base / "logs"
    return log_dir / LOG_FILE_NAME

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
    _logger = logger
    return logger

# --- FUNÇÃO PARA ENCONTRAR RECURSOS DENTRO DO .EXE ---
def _get_internal_base_path() -> Path:
    """Retorna o caminho base para recursos internos empacotados pelo PyInstaller."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # Dentro de um .exe 'onefile', os arquivos estão em uma pasta temporária _MEIPASS
        return Path(sys._MEIPASS)
    # Em modo de desenvolvimento ou .exe 'onedir'
    return _get_external_base_path()

def _manifest_path() -> Path:
    base_path = _get_internal_base_path()
    return base_path / "security" / _MANIFEST_FILENAME

def _load_manifest() -> Dict[str, object]:
    global _manifest_cache
    if _manifest_cache is None:
        manifest_path = _manifest_path()
        try:
            with manifest_path.open("r", encoding="utf-8") as file_handle:
                _manifest_cache = cast(Dict[str, object], json.load(file_handle))
        except FileNotFoundError:
            logger = _get_logger()
            logger.error(f"Violação de segurança: Arquivo de manifesto não encontrado em '{manifest_path}'. O programa será encerrado.")
            os._exit(1)
    return _manifest_cache

def _load_hmac_key() -> Optional[bytes]:
    global _hmac_key_cache
    if _hmac_key_cache is not _HMAC_KEY_UNINITIALIZED:
        return cast(Optional[bytes], _hmac_key_cache)
    _hmac_key_cache = _get_embedded_hmac_key()
    return _hmac_key_cache

def _calculate_file_hash(path: Path, algorithm: str) -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as file_handle:
        h.update(file_handle.read().replace(b"\r\n", b"\n"))
    return h.hexdigest()

def _verify_signature(expected_hash: str, signature: str) -> bool:
    key = _load_hmac_key()
    if not key: return False
    expected_signature = hmac.new(key, expected_hash.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_signature, signature)

def _collect_resource_violations(manifest: Dict[str, object]) -> List[str]:
    violations: List[str] = []
    # A verificação de arquivos de código-fonte é desabilitada em produção pois o PyInstaller os modifica.
    # Se a seção "resources" estiver vazia, esta função não faz nada.
    resources = manifest.get("resources", {})
    if not resources:
        return []

    base_path = _get_internal_base_path()
    algorithm = manifest.get("algorithm", "sha256")

    for name, resource in resources.items():
        path = base_path / resource["path"]
        expected_hash, signature = resource.get("hash"), resource.get("signature")

        if not (expected_hash and signature and _verify_signature(expected_hash, signature)):
            violations.append(f"Assinatura inválida para recurso '{name}'")
            continue
        if not path.exists():
            violations.append(f"Recurso não encontrado: {path}")
            continue
        calculated_hash = _calculate_file_hash(path, algorithm)
        if not hmac.compare_digest(calculated_hash, expected_hash):
            violations.append(f"Hash divergente para '{name}'")
    return violations

def _collect_debugger_violations() -> List[str]:
    # Esta verificação continua sendo importante
    violations: List[str] = []
    if sys.gettrace() is not None or "pydevd" in sys.modules:
        violations.append("Depurador Python detectado.")
    if sys.platform.startswith("win") and ctypes.windll.kernel32.IsDebuggerPresent():
        violations.append("Depurador nativo do Windows detectado.")
    return violations

def _perform_all_checks():
    violations: List[str] = []
    manifest = _load_manifest()
    violations.extend(_collect_debugger_violations())
    violations.extend(_collect_resource_violations(manifest))
    return violations

def enforce_runtime_safety():
    """Executa verificações de segurança na inicialização."""
    violations = _perform_all_checks()
    if violations:
        logger = _get_logger()
        for item in violations:
            logger.error("Violação de segurança: %s", item)
        os._exit(1) # Encerra silenciosamente em caso de violação
    _get_logger().info("Verificações de segurança iniciais concluídas com sucesso.")

def _schedule_next_timer_locked() -> None:
    global _integrity_timer

    timer = threading.Timer(INTEGRITY_CHECK_INTERVAL_SECONDS, _run_periodic_integrity_check)
    timer.daemon = True
    _integrity_timer = timer
    timer.start()


def _run_periodic_integrity_check() -> None:
    logger = _get_logger()
    logger.info("Iniciando revalidação periódica de integridade.")
    violations = _perform_all_checks()
    if violations:
        for item in violations:
            logger.error("Violação de segurança: %s", item)
        os._exit(1)
    logger.info("Revalidação periódica concluída sem violações.")

    with _integrity_lock:
        if _integrity_scheduler_started:
            _schedule_next_timer_locked()


def schedule_integrity_check() -> None:
    global _integrity_scheduler_started

    with _integrity_lock:
        if _integrity_scheduler_started:
            return

        _integrity_scheduler_started = True
        logger = _get_logger()
        logger.info(
            "Agendando verificações de integridade a cada %s segundos.",
            INTEGRITY_CHECK_INTERVAL_SECONDS,
        )
        _schedule_next_timer_locked()
