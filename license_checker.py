import base64
import json
import os
import secrets
import sys
import hashlib
import logging
import platform
import uuid
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set, Tuple
from concurrent.futures import CancelledError, ThreadPoolExecutor
from functools import lru_cache

import requests
import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as ttk
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from ttkbootstrap.constants import *

def resource_path(relative_path):
    """ Obtém o caminho absoluto para o recurso, funciona para dev e para PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

logger = logging.getLogger(__name__)

ACCOUNT_ID = "9798e344-f107-4cfd-bcd3-af9b8e75d352"
PRODUCT_TOKEN_ENV_VAR = "KEYGEN_PRODUCT_TOKEN"
PRODUCT_TOKEN_FILE_ENV_VAR = "KEYGEN_PRODUCT_TOKEN_FILE"
TOKEN_BROKER_URL_ENV_VAR = "KEYGEN_TOKEN_BROKER_URL"
TOKEN_BROKER_SHARED_SECRET_ENV_VAR = "KEYGEN_TOKEN_BROKER_SECRET"
API_BASE_URL = os.getenv(
    "LICENSE_API_BASE_URL", f"https://api.keygen.sh/v1/accounts/{ACCOUNT_ID}"
)
ICON_FILE = resource_path("icone.ico")
REQUEST_TIMEOUT = 10
SPINNER_POLL_INTERVAL_MS = 100

_EXECUTOR = ThreadPoolExecutor(max_workers=2)

_DELEGATED_TOKEN_CACHE: Dict[str, Tuple[str, float]] = {}
_DELEGATED_TOKEN_CLOCK_SKEW_SECONDS = 15

_PRODUCT_TOKEN_PLACEHOLDER_VALUES = {
    "EDITOR_AUTOMATICO_PRODUCT_TOKEN_PLACEHOLDER",
    "YOUR_PRODUCT_TOKEN_HERE",
    "REPLACE_ME",
    "CHANGE_ME",
    "CHANGEME",
}
_PRODUCT_TOKEN_PLACEHOLDER_SUBSTRINGS = ("PLACEHOLDER",)

LICENSE_AUTHORITY_PUBLIC_KEY_B64 = "9haWUaPN5nebwlUvq1mLoYcG1sqpPNoIwHrOzmN3E2I="
LICENSE_REVOCATION_URL_ENV_VAR = "LICENSE_REVOCATION_URL"
LICENSE_REVOCATION_FILE_ENV_VAR = "LICENSE_REVOCATION_FILE"
LICENSE_REVOCATION_REFRESH_SECONDS = int(os.getenv("LICENSE_REVOCATION_REFRESH", "3600"))
LICENSE_REVOCATION_TIMEOUT = 5
MIGRATION_REQUIRED_MESSAGE = (
    "O formato antigo de chaves do Keygen não é suportado. Solicite um novo token "
    "offline emitido pela equipa de suporte."
)

_REVOCATION_CACHE: Dict[str, Any] = {"timestamp": 0.0, "serials": set(), "error": None}


class SpinnerDialog(ttk.Toplevel):
    def __init__(self, parent, message: str):
        super().__init__(parent)
        self.transient(parent)
        self.title("Aguarde")
        self.resizable(False, False)
        self._closed = False

        try:
            self.iconbitmap(ICON_FILE)
        except tk.TclError:
            logger.debug("Não foi possível carregar o ícone do spinner em %s.", ICON_FILE)

        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=BOTH, expand=True)

        label = ttk.Label(frame, text=message, font=("Segoe UI", 10), wraplength=260)
        label.pack(pady=(0, 12))

        self.progress = ttk.Progressbar(frame, mode="indeterminate", length=220)
        self.progress.pack(fill=X)
        self.progress.start(12)

        self.protocol("WM_DELETE_WINDOW", lambda: None)

        self.update_idletasks()

        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        dialog_w = self.winfo_width()
        dialog_h = self.winfo_height()
        x = parent_x + (parent_w - dialog_w) // 2
        y = parent_y + (parent_h - dialog_h) // 2
        self.geometry(f"+{x}+{y}")

        self.grab_set()

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.progress.stop()
        except Exception:
            pass
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


def _run_with_spinner(parent_window, message: str, func, *args, timeout: Optional[float] = None, **kwargs):
    dialog = SpinnerDialog(parent_window, message)
    future = _EXECUTOR.submit(func, *args, **kwargs)
    timed_out = {"value": False}

    def poll_future():
        if dialog._closed:
            return
        if future.done():
            dialog.close()
        else:
            parent_window.after(SPINNER_POLL_INTERVAL_MS, poll_future)

    parent_window.after(SPINNER_POLL_INTERVAL_MS, poll_future)

    if timeout is not None:
        def on_timeout():
            if dialog._closed or future.done():
                return
            timed_out["value"] = True
            future.cancel()
            logger.warning("Tempo limite atingido para a operação de licença.")
            dialog.close()

        parent_window.after(int(timeout * 1000), on_timeout)

    dialog.wait_window()

    if timed_out["value"]:
        return None, TimeoutError("Tempo limite excedido.")

    try:
        return future.result(), None
    except CancelledError:
        return None, TimeoutError("Operação cancelada.")
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Erro inesperado ao executar operação de licença.")
        return None, exc

class CustomLicenseDialog(ttk.Toplevel):
    # ... (O conteúdo desta classe não muda)
    def __init__(self, parent):
        super().__init__(parent)
        self.transient(parent)
        self.title("Ativação de Licença")
        self.result = None
        self.resizable(False, False)

        try:
            self.iconbitmap(ICON_FILE)
        except tk.TclError:
            print(f"Aviso: Não foi possível carregar o ícone: {ICON_FILE}")

        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=BOTH, expand=True)

        header_label = ttk.Label(main_frame, text="Ativação do Produto", font=("Segoe UI", 14, "bold"), bootstyle="primary")
        header_label.pack(pady=(0, 5))

        info_label = ttk.Label(main_frame, text="Por favor, insira a sua chave de licença:", font=("Segoe UI", 10))
        info_label.pack(pady=(0, 15))

        self.entry = ttk.Entry(main_frame, width=50, font=("Segoe UI", 10))
        self.entry.pack(pady=(0, 20), ipady=4)
        self.entry.focus_set()

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x')
        
        spacer_frame = ttk.Frame(button_frame)
        spacer_frame.pack(side=LEFT, expand=True)

        cancel_button = ttk.Button(button_frame, text="Cancelar", width=10, command=self.on_cancel, bootstyle="secondary")
        cancel_button.pack(side=RIGHT, padx=(10, 0))

        ok_button = ttk.Button(button_frame, text="Ativar", width=10, command=self.on_ok, bootstyle="success")
        ok_button.pack(side=RIGHT)

        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.bind("<Return>", self.on_ok)
        self.bind("<Escape>", self.on_cancel)

        self.update_idletasks()
        # Centraliza na janela pai, não na tela inteira
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        dialog_w = self.winfo_width()
        dialog_h = self.winfo_height()
        x = parent_x + (parent_w - dialog_w) // 2
        y = parent_y + (parent_h - dialog_h) // 2
        self.geometry(f"+{x}+{y}")

        self.grab_set()
        self.wait_window(self)

    def on_ok(self, event=None):
        self.result = self.entry.get()
        self.destroy()

    def on_cancel(self, event=None):
        self.result = None
        self.destroy()


class ProductTokenDialog(ttk.Toplevel):
    """Janela para configuração do token de produto (API) do Keygen."""

    def __init__(self, parent):
        super().__init__(parent)
        self.transient(parent)
        self.title("Configurar Token de Produto")
        self.result = None
        self.resizable(False, False)

        try:
            self.iconbitmap(ICON_FILE)
        except tk.TclError:
            logger.debug("Não foi possível carregar o ícone para o diálogo de token de produto.")

        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=BOTH, expand=True)

        header = ttk.Label(
            main_frame,
            text="Token de Produto Necessário",
            font=("Segoe UI", 13, "bold"),
            bootstyle="primary",
        )
        header.pack(pady=(0, 8))

        info_text = (
            "Informe o token de produto da sua conta Keygen. "
            "Este token pode ser gerado no painel do Keygen em "
            "Settings → Product Tokens."
        )
        info_label = ttk.Label(
            main_frame,
            text=info_text,
            wraplength=360,
            font=("Segoe UI", 10),
            justify=tk.LEFT,
        )
        info_label.pack(pady=(0, 14))

        entry_label = ttk.Label(
            main_frame,
            text="Token de Produto:",
            font=("Segoe UI", 10, "bold"),
        )
        entry_label.pack(anchor=tk.W)

        self.entry = ttk.Entry(main_frame, width=55, font=("Segoe UI", 10))
        self.entry.pack(pady=(4, 18), ipady=4, fill=X)
        self.entry.focus_set()

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=X)

        cancel_button = ttk.Button(
            button_frame,
            text="Cancelar",
            width=12,
            command=self.on_cancel,
            bootstyle="secondary",
        )
        cancel_button.pack(side=RIGHT, padx=(10, 0))

        ok_button = ttk.Button(
            button_frame,
            text="Guardar",
            width=12,
            command=self.on_ok,
            bootstyle="success",
        )
        ok_button.pack(side=RIGHT)

        self.bind("<Return>", self.on_ok)
        self.bind("<Escape>", self.on_cancel)
        self.protocol("WM_DELETE_WINDOW", self.on_cancel)

        self.update_idletasks()
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        dialog_w = self.winfo_width()
        dialog_h = self.winfo_height()
        x = parent_x + (parent_w - dialog_w) // 2
        y = parent_y + (parent_h - dialog_h) // 2
        self.geometry(f"+{x}+{y}")

        self.grab_set()
        self.wait_window(self)

    def on_ok(self, event=None):
        self.result = self.entry.get()
        self.destroy()

    def on_cancel(self, event=None):
        self.result = None
        self.destroy()

def get_app_data_path():
    # ... (O conteúdo desta função não muda)
    app_data_folder_name = "EditorAutomatico"
    if platform.system() == "Windows":
        base_dir = os.getenv('APPDATA')
    else:
        base_dir = os.path.expanduser("~")
    app_data_dir = os.path.join(base_dir or os.path.expanduser("~"), app_data_folder_name)
    os.makedirs(app_data_dir, exist_ok=True)
    return app_data_dir

APP_DATA_PATH = get_app_data_path()
LICENSE_FILE_PATH = os.path.join(APP_DATA_PATH, "license.json")
USER_PRODUCT_TOKEN_PATH = os.path.join(APP_DATA_PATH, "product_token.dat")


class LicenseTamperedError(RuntimeError):
    """Raised when the persisted license payload fails integrity checks."""


class LicenseValidationError(RuntimeError):
    """Raised when an offline license token fails verification."""


class LicenseRevokedError(LicenseValidationError):
    """Raised when the token serial is listed in the revocation cache."""


def _load_secret_from_file(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as secret_file:
            content = secret_file.read().strip()
            return content or None
    except OSError:
        return None


def _sanitize_product_token(token: Optional[str], source: str) -> Optional[str]:
    """Normaliza tokens e ignora valores de placeholder configurados por engano."""

    if not token:
        return None

    candidate = token.strip()
    if not candidate:
        return None

    candidate_upper = candidate.upper()
    if candidate_upper in _PRODUCT_TOKEN_PLACEHOLDER_VALUES or any(
        substring in candidate_upper for substring in _PRODUCT_TOKEN_PLACEHOLDER_SUBSTRINGS
    ):
        logger.debug(
            "Token de produto obtido de %s corresponde a um placeholder e será ignorado.",
            source,
        )
        return None

    return candidate


@lru_cache(maxsize=1)
def get_product_token() -> str:
    token = _sanitize_product_token(
        os.getenv(PRODUCT_TOKEN_ENV_VAR),
        f"variável de ambiente {PRODUCT_TOKEN_ENV_VAR}",
    )
    if token:
        return token

    secret_file = os.getenv(PRODUCT_TOKEN_FILE_ENV_VAR)
    if secret_file:
        file_token = _sanitize_product_token(
            _load_secret_from_file(secret_file),
            f"ficheiro apontado por {PRODUCT_TOKEN_FILE_ENV_VAR}",
        )
        if file_token:
            return file_token

    user_configured_token = _sanitize_product_token(
        _load_secret_from_file(USER_PRODUCT_TOKEN_PATH),
        f"ficheiro de configuração {USER_PRODUCT_TOKEN_PATH}",
    )
    if user_configured_token:
        return user_configured_token

    raise RuntimeError(
        "A variável de ambiente 'KEYGEN_PRODUCT_TOKEN' (ou ficheiro apontado por "
        "'KEYGEN_PRODUCT_TOKEN_FILE') deve estar definida antes de utilizar a "
        "validação de licenças."
    )


def _get_product_token_optional() -> Optional[str]:
    """Retorna o token de produto se disponível, sem lançar exceções."""
    try:
        return get_product_token()
    except RuntimeError:
        logger.info(
            "Token de produto não configurado ou definido com placeholder. "
            "Será utilizada a autenticação com a chave de licença."
        )
        return None


def _clear_delegated_token_cache() -> None:
    _DELEGATED_TOKEN_CACHE.clear()


def _clear_revocation_cache() -> None:
    _REVOCATION_CACHE["timestamp"] = 0.0
    _REVOCATION_CACHE["serials"] = set()
    _REVOCATION_CACHE["error"] = None


@lru_cache()
def _embedded_public_key() -> ed25519.Ed25519PublicKey:
    public_bytes = base64.b64decode(LICENSE_AUTHORITY_PUBLIC_KEY_B64)
    return ed25519.Ed25519PublicKey.from_public_bytes(public_bytes)


def _decode_token_segments(token: str) -> Tuple[bytes, bytes]:
    try:
        payload_segment, signature_segment = token.split(".")
    except ValueError as exc:
        raise LicenseValidationError("Token de licença inválido.") from exc
    return _urlsafe_b64decode(payload_segment), _urlsafe_b64decode(signature_segment)


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _verify_offline_token(token: str) -> Dict[str, Any]:
    payload, signature = _decode_token_segments(token)
    public_key = _embedded_public_key()
    try:
        public_key.verify(signature, payload)
    except InvalidSignature as exc:
        raise LicenseValidationError("Assinatura da licença inválida.") from exc
    try:
        claims: Dict[str, Any] = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LicenseValidationError("Conteúdo inválido no token de licença.") from exc
    return claims


def _load_revocation_serials() -> Tuple[Set[str], Optional[str]]:
    now = time.time()
    if _REVOCATION_CACHE["serials"] and (now - _REVOCATION_CACHE["timestamp"]) < LICENSE_REVOCATION_REFRESH_SECONDS:
        return _REVOCATION_CACHE["serials"], _REVOCATION_CACHE.get("error")

    source_url = os.getenv(LICENSE_REVOCATION_URL_ENV_VAR)
    previous_serials: Set[str] = set(_REVOCATION_CACHE.get("serials", set()))
    revocations: Set[str] = previous_serials
    error_message: Optional[str] = None
    try:
        if source_url:
            response = requests.get(source_url, timeout=LICENSE_REVOCATION_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
        else:
            file_path = os.getenv(LICENSE_REVOCATION_FILE_ENV_VAR)
            if not file_path:
                file_path = resource_path(os.path.join("security", "license_revocations.json"))
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            else:
                payload = {"revoked": []}
        revoked_serials = payload.get("revoked", [])
        if isinstance(revoked_serials, list):
            revocations = {str(serial) for serial in revoked_serials}
    except Exception as exc:
        logger.debug("Falha ao atualizar lista de revogação: %s", exc)
        error_message = str(exc)

    _REVOCATION_CACHE["timestamp"] = now
    _REVOCATION_CACHE["serials"] = revocations
    _REVOCATION_CACHE["error"] = error_message
    return revocations, error_message


def _ensure_not_revoked(serial: Optional[str]) -> None:
    if not serial:
        return
    serials, _error = _load_revocation_serials()
    if serial in serials:
        raise LicenseRevokedError("Esta licença foi revogada pela autoridade.")


def _validate_claims(token: str, claims: Dict[str, Any], fingerprint: str) -> Dict[str, Any]:
    claim_fingerprint = claims.get("fingerprint")
    if not claim_fingerprint:
        raise LicenseValidationError("O token de licença não possui uma impressão digital associada.")
    if claim_fingerprint != fingerprint:
        raise LicenseValidationError("O token de licença não corresponde a esta máquina.")

    expiry_text = claims.get("exp")
    if not expiry_text:
        raise LicenseValidationError("O token de licença não possui data de expiração.")
    expiry_timestamp = _parse_iso_datetime(expiry_text)
    if expiry_timestamp is None:
        raise LicenseValidationError("Data de expiração inválida no token de licença.")
    if expiry_timestamp < time.time():
        raise LicenseValidationError("A licença expirou.")

    _ensure_not_revoked(str(claims.get("serial")))

    claims["token"] = token
    return claims
def _parse_iso_datetime(value: str) -> Optional[float]:
    try:
        sanitized = value.strip()
        if sanitized.endswith("Z"):
            sanitized = sanitized[:-1] + "+00:00"
        dt = datetime.fromisoformat(sanitized)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _request_delegated_credential(
    license_key: str,
) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    broker_url = os.getenv(TOKEN_BROKER_URL_ENV_VAR)
    if not broker_url:
        return None, None, (
            "O serviço de credenciais delegadas não está configurado. "
            "Contacte o administrador do sistema."
        )

    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    shared_secret = os.getenv(TOKEN_BROKER_SHARED_SECRET_ENV_VAR)
    if shared_secret:
        headers["X-Broker-Secret"] = shared_secret

    payload = {"licenseKey": license_key}

    try:
        response = requests.post(
            broker_url,
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.exceptions.Timeout:
        logger.warning("Tempo limite ao solicitar uma credencial delegada.")
        return None, None, "O serviço de credenciais demorou demasiado tempo a responder."
    except requests.exceptions.RequestException as exc:
        logger.exception("Erro ao contactar o serviço de credenciais: %s", exc)
        return None, None, "Não foi possível contactar o serviço de credenciais delegadas."

    try:
        data = response.json()
    except ValueError:
        logger.error("Resposta inválida recebida do serviço de credenciais delegadas.")
        return None, None, "Resposta inválida do serviço de credenciais delegadas."

    token = data.get("token") or data.get("accessToken") or data.get("credential")
    if not token:
        logger.error("O serviço de credenciais respondeu sem fornecer um token válido.")
        return None, None, "O serviço de credenciais não devolveu uma credencial válida."

    expiry_timestamp: Optional[float] = None
    expires_at_raw = data.get("expiresAt") or data.get("expiry")
    expires_in_raw = data.get("expiresIn")

    if isinstance(expires_in_raw, (int, float)):
        expiry_timestamp = time.time() + float(expires_in_raw)
    elif isinstance(expires_in_raw, str):
        try:
            expiry_timestamp = time.time() + float(expires_in_raw)
        except ValueError:
            logger.debug("Valor inesperado para expiresIn recebido do broker: %s", expires_in_raw)

    if isinstance(expires_at_raw, str):
        parsed_timestamp = _parse_iso_datetime(expires_at_raw)
        if parsed_timestamp:
            expiry_timestamp = parsed_timestamp

    return token, expiry_timestamp, None


def _get_delegated_credential(license_key: str) -> Tuple[Optional[str], Optional[str]]:
    if not license_key:
        return None, "É necessária uma chave de licença para obter credenciais delegadas."

    now = time.time()
    cached = _DELEGATED_TOKEN_CACHE.get(license_key)
    if cached:
        token, expiry = cached
        if expiry - _DELEGATED_TOKEN_CLOCK_SKEW_SECONDS > now:
            return token, None
        _DELEGATED_TOKEN_CACHE.pop(license_key, None)

    token, expiry_timestamp, error = _request_delegated_credential(license_key)
    if token:
        expiry_timestamp = expiry_timestamp or (now + 120)
        _DELEGATED_TOKEN_CACHE[license_key] = (token, expiry_timestamp)
        return token, None

    return None, error


def store_product_token(token: str) -> None:
    sanitized = _sanitize_product_token(token, "token fornecido pelo utilizador")
    if not sanitized:
        raise ValueError("Token de produto inválido.")

    try:
        os.makedirs(APP_DATA_PATH, exist_ok=True)
        with open(USER_PRODUCT_TOKEN_PATH, "w", encoding="utf-8") as token_file:
            token_file.write(sanitized + "\n")
    except OSError as exc:
        raise RuntimeError("Não foi possível guardar o token de produto.") from exc

    get_product_token.cache_clear()


def prompt_for_product_token(parent_window) -> bool:
    """Solicita ao utilizador o token de produto e guarda-o se fornecido."""

    while True:
        dialog = ProductTokenDialog(parent_window)
        token_input = (dialog.result or "").strip()

        if not token_input:
            return False

        try:
            store_product_token(token_input)
        except ValueError:
            messagebox.showerror(
                "Token inválido",
                "O token de produto fornecido é inválido. Verifique e tente novamente.",
                parent=parent_window,
            )
            continue
        except RuntimeError as exc:
            logger.exception("Falha ao guardar o token de produto.")
            messagebox.showerror(
                "Erro ao guardar token",
                str(exc),
                parent=parent_window,
            )
            return False

        messagebox.showinfo(
            "Token guardado",
            "O token de produto foi configurado com sucesso.",
            parent=parent_window,
        )
        return True


def _derive_encryption_key(fingerprint: str) -> bytes:
    return hashlib.sha256(fingerprint.encode("utf-8")).digest()


def _fingerprint_marker(fingerprint: str) -> str:
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()


def _encrypt_license_payload(data: Dict[str, Any], fingerprint: str) -> Dict[str, str]:
    plaintext = json.dumps(data).encode("utf-8")
    key = _derive_encryption_key(fingerprint)
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return {
        "version": 1,
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        "fingerprint_hash": _fingerprint_marker(fingerprint),
    }


def _decrypt_license_payload(payload: Dict[str, Any], fingerprint: str) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise LicenseTamperedError("Formato inesperado do ficheiro de licença.")

    fingerprint_hash = payload.get("fingerprint_hash")
    if fingerprint_hash and fingerprint_hash != _fingerprint_marker(fingerprint):
        raise LicenseTamperedError("Impressão digital incompatível com o ficheiro de licença.")

    try:
        nonce = base64.b64decode(payload["nonce"])
        ciphertext = base64.b64decode(payload["ciphertext"])
    except Exception as exc:  # pragma: no cover - defensive
        raise LicenseTamperedError("Não foi possível decodificar o ficheiro de licença.") from exc

    aesgcm = AESGCM(_derive_encryption_key(fingerprint))
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as exc:
        raise LicenseTamperedError("Falha na verificação de integridade da licença.") from exc

    try:
        return json.loads(plaintext.decode("utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        raise LicenseTamperedError("Conteúdo inválido no ficheiro de licença.") from exc

def _get_windows_machine_guid() -> Optional[str]:
    try:  # pragma: no cover - exercitado via testes com monkeypatch
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        )
        try:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
        finally:
            winreg.CloseKey(key)
        if isinstance(value, str) and value:
            return value
    except Exception:
        logger.debug("Falha ao ler MachineGuid do registo do Windows.", exc_info=True)
    return None


def _parse_smbios_system_uuid(blob: bytes) -> Optional[str]:
    offset = 0
    total = len(blob)
    while offset + 4 <= total:
        struct_type = blob[offset]
        struct_length = blob[offset + 1]
        if struct_length < 4 or offset + struct_length > total:
            break
        if struct_type == 1 and struct_length >= 0x19:
            raw = blob[offset + 8 : offset + 24]
            if len(raw) == 16 and any(raw):
                try:
                    return str(uuid.UUID(bytes_le=bytes(raw)))
                except ValueError:
                    logger.debug("UUID SMBIOS inválido encontrado.", exc_info=True)
        next_offset = offset + struct_length
        while next_offset < total:
            if blob[next_offset] == 0:
                if next_offset + 1 >= total or blob[next_offset + 1] == 0:
                    next_offset += 2
                    break
            next_offset += 1
        if next_offset <= offset:
            break
        offset = next_offset
    return None


def _get_windows_firmware_uuid() -> Optional[str]:
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        rsmb = int.from_bytes(b"RSMB", "little")
        size = kernel32.GetSystemFirmwareTable(rsmb, 0, None, 0)
        if not size:
            return None
        buffer = (ctypes.c_ubyte * size)()
        read = kernel32.GetSystemFirmwareTable(rsmb, 0, ctypes.byref(buffer), size)
        if read != size:
            return None
        return _parse_smbios_system_uuid(bytes(buffer))
    except Exception:
        logger.debug("Não foi possível obter o UUID SMBIOS através do firmware.", exc_info=True)
        return None


def _get_windows_volume_serial() -> Optional[str]:
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        serial_number = wintypes.DWORD()
        max_component_length = wintypes.DWORD()
        file_system_flags = wintypes.DWORD()
        volume_name_buffer = ctypes.create_unicode_buffer(1024)
        file_system_name_buffer = ctypes.create_unicode_buffer(1024)
        root_path = os.environ.get("SystemDrive", "C:")
        if not root_path.endswith("\\"):
            root_path += "\\"
        success = kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(root_path),
            volume_name_buffer,
            len(volume_name_buffer),
            ctypes.byref(serial_number),
            ctypes.byref(max_component_length),
            ctypes.byref(file_system_flags),
            file_system_name_buffer,
            len(file_system_name_buffer),
        )
        if success:
            return f"{serial_number.value:08X}"
    except Exception:
        logger.debug("Não foi possível obter o número de série do volume do sistema.", exc_info=True)
    return None


def _get_portable_fingerprint_source() -> str:
    node = uuid.getnode()
    uname = platform.uname()
    components = [f"{node:012x}"]
    components.extend(
        filter(
            None,
            [
                uname.system,
                uname.node,
                uname.machine,
                uname.processor,
                uname.version,
            ],
        )
    )
    return "-".join(components)


def get_machine_fingerprint():
    identifier = None
    strategies = []
    if platform.system() == "Windows":
        strategies.extend(
            [
                ("MachineGuid", _get_windows_machine_guid),
                ("FirmwareUUID", _get_windows_firmware_uuid),
                ("VolumeSerial", _get_windows_volume_serial),
            ]
        )
    strategies.append(("PortableFallback", _get_portable_fingerprint_source))

    for label, strategy in strategies:
        try:
            candidate = strategy()
        except Exception:  # pragma: no cover - defensive
            logger.debug("Erro inesperado ao calcular identificador %s.", label, exc_info=True)
            continue
        if candidate:
            identifier = str(candidate)
            logger.debug("Fingerprint obtido usando estratégia %s.", label)
            break

    if not identifier:
        identifier = _get_portable_fingerprint_source()
        logger.warning(
            "Todas as estratégias de fingerprint falharam; a alternativa multiplataforma foi utilizada."
        )

    return hashlib.sha256(identifier.encode("utf-8")).hexdigest()

def validate_license_with_id(license_id, fingerprint, license_key: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    token = license_key or license_id
    if not token:
        return None, "Não foi possível localizar o token de licença armazenado."

    if "." not in token:
        logger.info("Licença armazenada utiliza o formato antigo e requer migração.")
        return {"meta": {"valid": False, "detail": MIGRATION_REQUIRED_MESSAGE}}, None

    try:
        claims = _verify_offline_token(token)
        validated_claims = _validate_claims(token, claims, fingerprint)
    except LicenseRevokedError as exc:
        logger.warning(
            "Licença revogada detectada durante validação periódica: serial=%s",
            claims.get("serial") if "claims" in locals() else "?",
        )
        return {"meta": {"valid": False, "detail": str(exc)}}, None
    except LicenseValidationError as exc:
        logger.warning("Falha na validação local da licença: %s", exc)
        return {"meta": {"valid": False, "detail": str(exc)}}, None
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Erro inesperado ao validar token de licença armazenado.")
        return None, str(exc)

    response_payload = {
        "data": {"id": validated_claims.get("customer_id"), "attributes": validated_claims},
        "meta": {"valid": True, "claims": validated_claims, "key": token},
    }
    return response_payload, None


def activate_new_license(license_key, fingerprint):
    if not license_key or "." not in license_key:
        return None, MIGRATION_REQUIRED_MESSAGE, "migration_required"

    try:
        claims = _verify_offline_token(license_key)
        validated_claims = _validate_claims(license_key, claims, fingerprint)
    except LicenseRevokedError as exc:
        logger.warning("Tentativa de ativação com licença revogada: %s", exc)
        return None, str(exc), None
    except LicenseValidationError as exc:
        logger.warning("Falha ao ativar licença localmente: %s", exc)
        return None, str(exc), None
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Erro inesperado ao ativar licença offline.")
        return None, str(exc), None

    activation_payload = {
        "data": {
            "id": validated_claims.get("customer_id"),
            "type": "licenses",
            "attributes": {
                "exp": validated_claims.get("exp"),
                "seats": validated_claims.get("seats"),
                "serial": validated_claims.get("serial"),
                "fingerprint": validated_claims.get("fingerprint"),
            },
        },
        "meta": {
            "valid": True,
            "key": license_key,
            "claims": validated_claims,
        },
    }
    return activation_payload, "Ativação bem-sucedida.", None


def save_license_data(license_data, fingerprint: Optional[str] = None):
    # ... (O conteúdo desta função não muda)
    fingerprint = fingerprint or get_machine_fingerprint()
    encrypted_payload = _encrypt_license_payload(license_data, fingerprint)
    try:
        with open(LICENSE_FILE_PATH, "w", encoding='utf-8') as f:
            json.dump(encrypted_payload, f, indent=2)
    except Exception:
        messagebox.showerror("Erro ao Guardar", f"Não foi possível guardar o ficheiro de licença em:\n{LICENSE_FILE_PATH}")


def load_license_data(fingerprint: Optional[str] = None):
    # ... (O conteúdo desta função não muda)
    fingerprint = fingerprint or get_machine_fingerprint()
    if os.path.exists(LICENSE_FILE_PATH):
        try:
            with open(LICENSE_FILE_PATH, "r", encoding='utf-8') as f:
                encrypted_payload: Dict[str, Any] = json.load(f)
            return _decrypt_license_payload(encrypted_payload, fingerprint)
        except LicenseTamperedError:
            try:
                os.remove(LICENSE_FILE_PATH)
            except OSError:
                logger.warning("Não foi possível remover um ficheiro de licença corrompido em %s.", LICENSE_FILE_PATH)
            raise
        except Exception:
            return None
    return None

def check_license(parent_window): # MODIFICADO: Recebe a janela pai
    """Função principal que gere o fluxo de verificação de licença."""
    fingerprint = get_machine_fingerprint()
    try:
        stored_data = load_license_data(fingerprint)
    except LicenseTamperedError:
        messagebox.showwarning(
            "Licença inválida",
            "Os dados de licença guardados não passaram na verificação de integridade e serão ignorados.",
            parent=parent_window,
        )
        stored_data = None

    stored_license_key = None
    if stored_data:
        license_id = stored_data.get("data", {}).get("id")
        stored_license_key = stored_data.get("meta", {}).get("key")
        if license_id:
            validation_payload, spinner_error = _run_with_spinner(
                parent_window,
                "A validar a licença existente...",
                validate_license_with_id,
                license_id,
                fingerprint,
                stored_license_key,
                timeout=REQUEST_TIMEOUT,
            )

            if spinner_error:
                if isinstance(spinner_error, TimeoutError):
                    logger.warning("Tempo limite ao validar a licença armazenada.")
                    messagebox.showwarning(
                        "Tempo limite",
                        "A validação da licença excedeu o tempo limite. Será necessário tentar novamente.",
                        parent=parent_window,
                    )
                else:
                    logger.error("Erro inesperado ao validar licença armazenada: %s", spinner_error)
                    messagebox.showerror(
                        "Erro na Validação",
                        "Ocorreu um erro inesperado ao validar a licença existente.",
                        parent=parent_window,
                    )
            elif validation_payload:
                validation_result, validation_error = validation_payload
                if validation_result and validation_result.get("meta", {}).get("valid"):
                    return True, validation_result
                if validation_result:
                    detail_message = validation_result.get("meta", {}).get("detail")
                    if detail_message:
                        messagebox.showwarning(
                            "Validação Necessária",
                            f"{detail_message}\nSerá necessário introduzir novamente a sua chave de licença.",
                            parent=parent_window,
                        )
                if validation_error:
                    messagebox.showwarning(
                        "Validação Necessária",
                        f"{validation_error}\nSerá necessário introduzir novamente a sua chave de licença.",
                        parent=parent_window,
                    )
            else:
                logger.error("Validação de licença retornou resultado inesperado.")

    # REMOVIDO: A criação e destruição da janela temporária foi removida.

    license_key_input = stored_license_key or ""
    needs_license_input = not bool(license_key_input)

    while True:
        if needs_license_input:
            dialog = CustomLicenseDialog(parent_window)
            license_key_input = (dialog.result or "").strip()

            if not license_key_input:
                messagebox.showwarning(
                    "Ativação Necessária",
                    "É necessária uma chave de licença para usar este programa.",
                    parent=parent_window,
                )
                return False, None

        activation_payload, spinner_error = _run_with_spinner(
            parent_window,
            "A ativar a licença...",
            activate_new_license,
            license_key_input,
            fingerprint,
            timeout=REQUEST_TIMEOUT,
        )

        if spinner_error:
            if isinstance(spinner_error, TimeoutError):
                error_message = "O pedido ao servidor excedeu o tempo limite. Deseja tentar novamente?"
                logger.warning("Tempo limite durante a ativação da licença.")
            else:
                error_message = "Ocorreu um erro inesperado durante a ativação. Deseja tentar novamente?"
                logger.error("Erro inesperado durante a ativação da licença: %s", spinner_error)

            if not messagebox.askretrycancel("Falha na Ativação", error_message, parent=parent_window):
                return False, None
            needs_license_input = False
            continue

        if activation_payload:
            activation_data, message, error_code = activation_payload
        else:
            activation_data, message, error_code = None, "Erro desconhecido durante a ativação.", None

        if activation_data:
            messagebox.showinfo("Sucesso", "A sua licença foi ativada com sucesso nesta máquina!", parent=parent_window)
            activation_data.setdefault("meta", {})["key"] = license_key_input
            save_license_data(activation_data, fingerprint)
            return True, activation_data
        else:
            if error_code == "migration_required":
                messagebox.showwarning(
                    "Token incompatível",
                    MIGRATION_REQUIRED_MESSAGE,
                    parent=parent_window,
                )
                return False, None

            if error_code == "auth_required":
                if prompt_for_product_token(parent_window):
                    needs_license_input = False
                    continue
                retry_message = (
                    "O token de produto é necessário para concluir a ativação. "
                    "Deseja tentar novamente?"
                )
                if not messagebox.askretrycancel("Falha na Ativação", retry_message, parent=parent_window):
                    return False, None
                needs_license_input = True
                continue

            if not message:
                message = "Ocorreu um erro durante a ativação."

            if not messagebox.askretrycancel(
                "Falha na Ativação",
                f"{message}\nDeseja tentar novamente?",
                parent=parent_window,
            ):
                return False, None
            needs_license_input = True
