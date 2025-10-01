import base64
import json
import os
import secrets
import sys
import hashlib
import logging
import platform
import uuid
from datetime import datetime, timezone
from concurrent.futures import CancelledError, ThreadPoolExecutor
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

import requests
import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as ttk
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from ttkbootstrap.constants import *

def resource_path(relative_path):
    """ Obtém o caminho absoluto para o recurso, funciona para dev e para PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

logger = logging.getLogger(__name__)

PRODUCT_TOKEN_ENV_VAR = "KEYGEN_PRODUCT_TOKEN"
PRODUCT_TOKEN_FILE_ENV_VAR = "KEYGEN_PRODUCT_TOKEN_FILE"
PRODUCT_TOKEN_RESOURCE = "security/product_token.dat"
ICON_FILE = resource_path("icone.ico")
REQUEST_TIMEOUT = 10
SPINNER_POLL_INTERVAL_MS = 100

LICENSE_TOKEN_VERSION = "LA1"
LICENSE_PUBLIC_KEY_RESOURCE = "security/license_public_key.pem"
REVOCATION_URL_ENV_VAR = "LICENSE_REVOCATION_URL"
REVOCATION_CACHE_FILENAME = "license_revocations.json"
REVOCATION_CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 horas
REVOCATION_REQUEST_TIMEOUT = 5

_EXECUTOR = ThreadPoolExecutor(max_workers=2)

_PRODUCT_TOKEN_PLACEHOLDER_VALUES = {
    "EDITOR_AUTOMATICO_PRODUCT_TOKEN_PLACEHOLDER",
    "YOUR_PRODUCT_TOKEN_HERE",
    "REPLACE_ME",
    "CHANGE_ME",
    "CHANGEME",
}
_PRODUCT_TOKEN_PLACEHOLDER_SUBSTRINGS = ("PLACEHOLDER",)


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
    """Raised when a locally signed license token is invalid."""


class RevocationFetchError(RuntimeError):
    """Raised when the revocation status list cannot be refreshed."""


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

    resource_token = _sanitize_product_token(
        _load_secret_from_file(resource_path(PRODUCT_TOKEN_RESOURCE)),
        "recurso incorporado product_token.dat",
    )
    if resource_token:
        return resource_token

    executable_dir = os.path.dirname(sys.executable)
    executable_candidates = [
        os.path.join(executable_dir, "security", "product_token.dat"),
        os.path.join(executable_dir, "product_token.dat"),
    ]

    for candidate in executable_candidates:
        file_token = _sanitize_product_token(
            _load_secret_from_file(candidate),
            f"ficheiro {candidate}",
        )
        if file_token:
            return file_token

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


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


@lru_cache(maxsize=1)
def _get_embedded_public_key() -> Ed25519PublicKey:
    path = resource_path(LICENSE_PUBLIC_KEY_RESOURCE)
    with open(path, "rb") as key_file:
        data = key_file.read()
    return serialization.load_pem_public_key(data)


def _decode_license_token(token: str) -> Tuple[Dict[str, Any], bytes]:
    if not token:
        raise LicenseValidationError("A chave de licença fornecida está vazia.")
    parts = token.split(".")
    if len(parts) != 3:
        raise LicenseValidationError("Formato de chave de licença inválido.")
    version, payload_b64, signature_b64 = parts
    if version != LICENSE_TOKEN_VERSION:
        raise LicenseValidationError("Esta versão da chave de licença não é suportada.")

    try:
        payload = _urlsafe_b64decode(payload_b64)
        signature = _urlsafe_b64decode(signature_b64)
    except (ValueError, TypeError) as exc:
        raise LicenseValidationError("Não foi possível decodificar o token de licença.") from exc

    public_key = _get_embedded_public_key()
    try:
        public_key.verify(signature, payload)
    except InvalidSignature as exc:
        raise LicenseValidationError("A assinatura da licença é inválida.") from exc

    try:
        claims = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LicenseValidationError("Os dados da licença estão corrompidos.") from exc

    if not isinstance(claims, dict):
        raise LicenseValidationError("Os dados da licença têm um formato inesperado.")

    return claims, payload


def _parse_expiry(claims: Dict[str, Any]) -> Optional[str]:
    expiry = claims.get("expiry")
    if not expiry:
        return None
    if not isinstance(expiry, str):
        raise LicenseValidationError("Data de expiração inválida na licença.")
    try:
        expiry_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LicenseValidationError("Data de expiração inválida na licença.") from exc
    expiry_dt = expiry_dt.astimezone(timezone.utc)
    if expiry_dt < datetime.now(timezone.utc):
        raise LicenseValidationError("A licença está expirada.")
    return expiry_dt.isoformat()


def _revocation_cache_path() -> str:
    return os.path.join(APP_DATA_PATH, REVOCATION_CACHE_FILENAME)


def _load_revocation_cache() -> Dict[str, Any]:
    path = _revocation_cache_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            cache = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        cache = {}
    if not isinstance(cache, dict):
        cache = {}
    cache.setdefault("revoked", [])
    cache.setdefault("minimum_serial", {})
    cache.setdefault("revoked_tokens", [])
    cache.setdefault("fetched_at", None)
    return cache


def _save_revocation_cache(data: Dict[str, Any]) -> None:
    path = _revocation_cache_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
    except OSError:
        logger.debug("Não foi possível guardar o cache de revogações em %s.", path, exc_info=True)


def _revocation_cache_expired(cache: Dict[str, Any]) -> bool:
    fetched_at = cache.get("fetched_at")
    if not fetched_at:
        return True
    try:
        fetched_dt = datetime.fromisoformat(str(fetched_at))
    except ValueError:
        return True
    age = datetime.now(timezone.utc) - fetched_dt.astimezone(timezone.utc)
    return age.total_seconds() > REVOCATION_CACHE_TTL_SECONDS


def _fetch_revocation_source(source: str) -> Dict[str, Any]:
    if source.startswith("file://"):
        source = source[7:]
    if os.path.exists(source):
        with open(source, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if not isinstance(data, dict):
                raise ValueError("O ficheiro de revogações deve conter um objeto JSON.")
            return data
    response = requests.get(source, timeout=REVOCATION_REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("A resposta de revogações deve ser um objeto JSON.")
    return data


def _get_revocation_data(*, force_refresh: bool = False) -> Dict[str, Any]:
    cache = _load_revocation_cache()
    source = os.getenv(REVOCATION_URL_ENV_VAR)
    if not source:
        return cache

    needs_refresh = force_refresh or _revocation_cache_expired(cache)
    if not needs_refresh:
        return cache

    try:
        fetched = _fetch_revocation_source(source)
    except Exception as exc:
        raise RevocationFetchError("Não foi possível actualizar a lista de revogações.") from exc

    fetched.setdefault("revoked", [])
    fetched.setdefault("minimum_serial", {})
    fetched.setdefault("revoked_tokens", [])
    fetched["fetched_at"] = datetime.now(timezone.utc).isoformat()
    _save_revocation_cache(fetched)
    return fetched


def _check_revocation_status(
    claims: Dict[str, Any],
    license_key: str,
    *,
    force_refresh: bool = False,
) -> Optional[str]:
    data = _get_revocation_data(force_refresh=force_refresh)
    license_id = claims.get("license_id")

    revoked_ids = set(data.get("revoked", []))
    if license_id and license_id in revoked_ids:
        return "Esta licença foi revogada pelo emissor."

    minimum_serial = data.get("minimum_serial", {})
    if license_id and license_id in minimum_serial:
        try:
            required_serial = int(minimum_serial[license_id])
            current_serial = int(claims.get("serial", 0))
        except (TypeError, ValueError):
            return "Os dados de série da licença são inválidos."
        if current_serial < required_serial:
            return "Uma nova chave de licença foi emitida. Solicite uma reemissão."

    revoked_tokens = set(data.get("revoked_tokens", []))
    if revoked_tokens:
        token_hash = hashlib.sha256(license_key.encode("utf-8")).hexdigest()
        if token_hash in revoked_tokens:
            return "Esta chave de licença foi revogada."

    return None


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

def validate_license_with_id(
    license_id,
    fingerprint,
    license_key: Optional[str] = None,
    *,
    force_refresh: bool = False,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not license_key:
        return None, "É necessária uma chave de licença válida."

    try:
        claims, _ = _decode_license_token(license_key)
    except LicenseValidationError as exc:
        return {"meta": {"valid": False, "detail": str(exc), "key": license_key}}, None
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Erro inesperado ao analisar a licença.")
        return None, "Ocorreu um erro inesperado ao analisar a licença."

    claim_fingerprint = claims.get("fingerprint")
    if not isinstance(claim_fingerprint, str) or not claim_fingerprint:
        return {"meta": {"valid": False, "detail": "A licença não contém uma impressão digital válida.", "key": license_key}}, None
    if claim_fingerprint != fingerprint:
        return {"meta": {"valid": False, "detail": "Esta licença está vinculada a outra máquina.", "key": license_key}}, None

    try:
        seat_count = int(claims.get("seat_count", 0))
    except (TypeError, ValueError):
        seat_count = 0
    if seat_count <= 0:
        return {"meta": {"valid": False, "detail": "O número de lugares definido para a licença é inválido.", "key": license_key}}, None

    try:
        serial = int(claims.get("serial", 0))
    except (TypeError, ValueError):
        return {"meta": {"valid": False, "detail": "O número de série da licença é inválido.", "key": license_key}}, None

    normalized_expiry = None
    try:
        normalized_expiry = _parse_expiry(claims)
    except LicenseValidationError as exc:
        return {"meta": {"valid": False, "detail": str(exc), "key": license_key}}, None

    claim_license_id = claims.get("license_id")
    if license_id and claim_license_id and claim_license_id != license_id:
        return {"meta": {"valid": False, "detail": "Esta licença não corresponde ao registo armazenado.", "key": license_key}}, None

    try:
        revocation_detail = _check_revocation_status(
            claims,
            license_key,
            force_refresh=force_refresh,
        )
    except RevocationFetchError as exc:
        logger.warning("Falha ao actualizar lista de revogações: %s", exc)
        return None, str(exc)

    if revocation_detail:
        return {"meta": {"valid": False, "detail": revocation_detail, "key": license_key}}, None

    license_identifier = claim_license_id or license_id or claims.get("customer_id")
    attributes = {
        "expiry": normalized_expiry,
        "customer": claims.get("customer_id"),
        "fingerprint": claim_fingerprint,
        "seatCount": seat_count,
        "serial": serial,
        "issuedAt": claims.get("issued_at"),
    }

    payload = {
        "data": {
            "type": "licenses",
            "id": license_identifier,
            "attributes": attributes,
        },
        "meta": {
            "valid": True,
            "detail": None,
            "key": license_key,
            "token_version": LICENSE_TOKEN_VERSION,
        },
    }

    return payload, None

def activate_new_license(license_key, fingerprint):
    validation, error = validate_license_with_id(
        None,
        fingerprint,
        license_key,
        force_refresh=True,
    )
    if error:
        return None, error, None
    if validation and validation.get("meta", {}).get("valid"):
        validation.setdefault("meta", {})["key"] = license_key
        return validation, "Licença verificada com sucesso.", None

    detail = None
    if validation:
        detail = validation.get("meta", {}).get("detail")
    return None, detail or "A chave de licença fornecida não é válida.", None

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
                force_refresh=True,
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
                if validation_error:
                    logger.warning("Validação adiada: %s", validation_error)
                    messagebox.showwarning(
                        "Validação adiada",
                        f"{validation_error}\nA licença guardada será utilizada temporariamente.",
                        parent=parent_window,
                    )
                    return True, stored_data
                if validation_result and validation_result.get("meta", {}).get("valid"):
                    save_license_data(validation_result, fingerprint)
                    return True, validation_result
                if validation_result:
                    detail_message = validation_result.get("meta", {}).get("detail")
                    if detail_message:
                        messagebox.showwarning(
                            "Validação Necessária",
                            f"{detail_message}\nSerá necessário introduzir novamente a sua chave de licença.",
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
                error_message = "A validação da licença excedeu o tempo limite. Deseja tentar novamente?"
                logger.warning("Tempo limite durante a validação da licença.")
            else:
                error_message = "Ocorreu um erro inesperado durante a validação. Deseja tentar novamente?"
                logger.error("Erro inesperado durante a validação da licença: %s", spinner_error)

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
            if not message:
                message = "Ocorreu um erro durante a ativação."

            if not messagebox.askretrycancel(
                "Falha na Ativação",
                f"{message}\nDeseja tentar novamente?",
                parent=parent_window,
            ):
                return False, None
            needs_license_input = True
