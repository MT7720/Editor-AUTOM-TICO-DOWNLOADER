import hashlib
import json
import os
import platform
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests
import tkinter as tk
import ttkbootstrap as ttk
from tkinter import messagebox
from ttkbootstrap.constants import *

from security.license_authority import verify_token
from security.license_manager import set_license_as_valid
from security import secrets
from security.secrets import SecretLoaderError

load_license_secrets = secrets.load_license_secrets


LICENSE_REVOCATION_FILE_ENV_VAR = "EDITOR_AUTOMATICO_LICENSE_REVOCATIONS"
_DEFAULT_REVOCATION_FILE = Path(__file__).with_name("security").joinpath("license_revocations.json")


def resource_path(relative_path: str) -> str:
    """Obtém o caminho absoluto para um recurso tanto em dev quanto no PyInstaller."""

    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)


ICON_FILE = resource_path("icone.ico")
_EXECUTOR = ThreadPoolExecutor(max_workers=2)

MIGRATION_REQUIRED_MESSAGE = "Esta versão do Editor Automático aceita apenas chaves emitidas diretamente pelo Keygen."


class LicenseTamperedError(Exception):
    """Mantida por compatibilidade com versões anteriores."""


class CustomLicenseDialog(ttk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        fingerprint: Optional[str] = None,
        activation_timeout: Optional[int] = None,
        initial_status: Optional[str] = None,
    ):
        super().__init__(parent)
        self.transient(parent)
        self.title("Ativação de Licença")
        self.result = None
        self.resizable(False, False)

        try:
            self.iconbitmap(ICON_FILE)
        except tk.TclError:
            pass

        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=BOTH, expand=True)

        header_label = ttk.Label(
            main_frame,
            text="Ativação do Produto",
            font=("Segoe UI", 14, "bold"),
            bootstyle="primary",
        )
        header_label.pack(pady=(0, 5))

        info_label = ttk.Label(
            main_frame,
            text="Por favor, insira a sua chave de licença:",
            font=("Segoe UI", 10),
        )
        info_label.pack(pady=(0, 15))

        self.entry = ttk.Entry(main_frame, width=50, font=("Segoe UI", 10))
        self.entry.pack(pady=(0, 20), ipady=4)
        self.entry.focus_set()

        status_text = (initial_status or "").strip()
        self.status_var = tk.StringVar(value=status_text)
        status_label = ttk.Label(
            main_frame,
            textvariable=self.status_var,
            font=("Segoe UI", 9),
            wraplength=360,
            bootstyle="secondary",
            justify=CENTER,
        )
        status_label.pack(fill=X, pady=(0, 10))

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x")

        ttk.Frame(button_frame).pack(side=LEFT, expand=True)

        cancel_button = ttk.Button(
            button_frame,
            text="Cancelar",
            width=10,
            command=self.on_cancel,
            bootstyle="secondary",
        )
        cancel_button.pack(side=RIGHT, padx=(10, 0))

        ok_button = ttk.Button(
            button_frame,
            text="Ativar",
            width=10,
            command=self.on_ok,
            bootstyle="success",
        )
        ok_button.pack(side=RIGHT)

        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.bind("<Return>", self.on_ok)
        self.bind("<Escape>", self.on_cancel)

        self.update_idletasks()
        parent_x, parent_y = parent.winfo_x(), parent.winfo_y()
        parent_w, parent_h = parent.winfo_width(), parent.winfo_height()
        dialog_w, dialog_h = self.winfo_width(), self.winfo_height()
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


def get_app_data_path() -> str:
    app_data_folder_name = "EditorAutomatico"
    if platform.system() == "Windows":
        base_dir = os.getenv("APPDATA")
    else:
        base_dir = os.path.expanduser("~")
    app_data_dir = os.path.join(base_dir or os.path.expanduser("~"), app_data_folder_name)
    os.makedirs(app_data_dir, exist_ok=True)
    return app_data_dir


APP_DATA_PATH = get_app_data_path()
LICENSE_FILE_PATH = os.path.join(APP_DATA_PATH, "license.json")


def _run_command(cmd: str) -> Optional[str]:
    try:
        output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return None
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[0] if lines else None


def get_machine_fingerprint() -> str:
    identifier = None
    if platform.system() == "Windows":
        identifier = _run_command("wmic csproduct get uuid")
        if identifier and len(identifier) <= 5:
            identifier = None
    if not identifier:
        identifier = f"{platform.system()}-{platform.node()}-{platform.machine()}"
    return hashlib.sha256(identifier.encode()).hexdigest()


@lru_cache(maxsize=1)
def get_license_service_credentials() -> secrets.LicenseServiceCredentials:
    """Load and cache the credentials required to talk to Keygen."""

    return load_license_secrets()


def get_product_token() -> str:
    return get_license_service_credentials().product_token


def get_api_base_url() -> str:
    return get_license_service_credentials().api_base_url


@lru_cache(maxsize=1)
def _load_revoked_serials() -> Tuple[str, ...]:
    path_value = os.getenv(LICENSE_REVOCATION_FILE_ENV_VAR)
    if path_value:
        candidate = Path(path_value)
    else:
        candidate = _DEFAULT_REVOCATION_FILE
    try:
        with candidate.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return tuple()
    except (OSError, json.JSONDecodeError):
        return tuple()
    revoked = data.get("revoked")
    if not isinstance(revoked, list):
        return tuple()
    cleaned = [str(item).strip() for item in revoked if isinstance(item, str) and item.strip()]
    return tuple(cleaned)


def _clear_revocation_cache() -> None:
    _load_revoked_serials.cache_clear()


def _is_serial_revoked(serial: Optional[str]) -> bool:
    if not serial:
        return False
    return serial in _load_revoked_serials()


def _is_legacy_license_key(license_key: str) -> bool:
    return "." in license_key


def _handle_legacy_license_key(license_key: str, fingerprint: str) -> Tuple[None, str, str]:
    try:
        claims = verify_token(license_key)
    except Exception:
        return None, MIGRATION_REQUIRED_MESSAGE, "migration_required"

    claim_serial = str(claims.get("serial", "")) if claims.get("serial") else ""
    if _is_serial_revoked(claim_serial):
        return None, MIGRATION_REQUIRED_MESSAGE, "migration_required"

    claim_fingerprint = claims.get("fingerprint")
    if claim_fingerprint and fingerprint and claim_fingerprint != fingerprint:
        return None, MIGRATION_REQUIRED_MESSAGE, "migration_required"

    return None, MIGRATION_REQUIRED_MESSAGE, "migration_required"


def _extract_error_detail(payload: Dict[str, Any]) -> Optional[str]:
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        detail = errors[0].get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
    meta = payload.get("meta")
    if isinstance(meta, dict):
        detail = meta.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
    return None


def _validate_key_with_keygen(
    license_key: str, fingerprint: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    try:
        credentials = get_license_service_credentials()
    except SecretLoaderError as exc:
        message = (
            "Não foi possível carregar as credenciais do serviço de licenças. "
            f"{exc}"
        )
        return None, message, None

    payload: Dict[str, Any] = {
        "data": {"type": "licenses"},
        "meta": {"key": license_key},
    }
    if fingerprint:
        payload["meta"]["fingerprint"] = fingerprint

    headers = {
        "Authorization": f"Bearer {credentials.product_token}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
    }

    try:
        response = requests.post(
            f"{credentials.api_base_url}/licenses/actions/validate-key",
            json=payload,
            headers=headers,
            timeout=10,
        )
    except requests.RequestException:
        return None, "Não foi possível contactar o servidor para validar a chave.", None

    try:
        data = response.json()
    except ValueError:
        return None, "Resposta inválida do servidor de licenças.", None

    if response.status_code >= 400:
        detail = _extract_error_detail(data)
        message = detail or "Não foi possível validar a chave de licença."
        return None, message, detail

    meta = data.get("meta", {}) if isinstance(data, dict) else {}
    if meta.get("valid") is not True:
        detail = _extract_error_detail(data) or "Chave inválida ou expirada."
        return None, detail, detail

    meta.setdefault("key", license_key)
    if fingerprint:
        meta.setdefault("fingerprint", fingerprint)
    data["meta"] = meta
    return data, None, None


def activate_new_license(
    license_key: str, fingerprint: str
) -> Tuple[Optional[Dict[str, Any]], str, Optional[str]]:
    normalized_key = (license_key or "").strip()
    if not normalized_key:
        return None, "Informe uma chave de licença válida.", None

    if _is_legacy_license_key(normalized_key):
        return _handle_legacy_license_key(normalized_key, fingerprint)

    payload, error, detail = _validate_key_with_keygen(normalized_key, fingerprint)
    if payload is None:
        return None, error or "Não foi possível validar a chave de licença.", detail

    return payload, "Licença ativada com sucesso.", None


def validate_license_key(
    license_key: Optional[str], fingerprint: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    normalized_key = (license_key or "").strip()
    if not normalized_key:
        message = "Informe uma chave de licença válida."
        return None, message, message

    if _is_legacy_license_key(normalized_key):
        return _handle_legacy_license_key(normalized_key, fingerprint)

    payload, error, detail = _validate_key_with_keygen(normalized_key, fingerprint)
    if payload is None:
        return None, error, detail

    return payload, None, None


def save_license_data(license_data: Dict[str, Any], fingerprint: Optional[str] = None) -> None:
    with open(LICENSE_FILE_PATH, "w", encoding="utf-8") as handle:
        json.dump(license_data, handle, indent=2)


def load_license_data(fingerprint: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not os.path.exists(LICENSE_FILE_PATH):
        return None
    try:
        with open(LICENSE_FILE_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def extract_license_key(data: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(data, dict):
        return None
    meta = data.get("meta")
    if isinstance(meta, dict):
        key = meta.get("key")
        if isinstance(key, str) and key.strip():
            return key.strip()
    raw_key = data.get("key")
    if isinstance(raw_key, str) and raw_key.strip():
        return raw_key.strip()
    payload = data.get("payload")
    if isinstance(payload, dict):
        return extract_license_key(payload)
    return None


def check_license(parent_window: tk.Misc) -> Tuple[bool, Optional[Dict[str, Any]]]:
    fingerprint = get_machine_fingerprint()
    stored_data = load_license_data(fingerprint)
    stored_key = extract_license_key(stored_data)
    initial_status: Optional[str] = None

    if stored_key:
        payload, error, detail = validate_license_key(stored_key, fingerprint)
        if payload and payload.get("meta", {}).get("valid"):
            save_license_data(payload)
            set_license_as_valid()
            return True, payload
        if error:
            print("Falha na revalidação:", error)
        initial_status = ""

    while True:
        dialog = CustomLicenseDialog(
            parent_window,
            fingerprint,
            activation_timeout=None,
            initial_status=initial_status,
        )
        dialog_result = getattr(dialog, "result", None)
        if dialog_result is None:
            dialog_result = getattr(dialog, "result_data", None)
        license_key_input = (dialog_result or "").strip()

        if not license_key_input:
            if parent_window is not None:
                messagebox.showwarning(
                    "Ativação Necessária",
                    "É necessária uma chave de licença para usar este programa.",
                    parent=parent_window,
                )
            return False, None

        parent_window.config(cursor="watch")
        future = _EXECUTOR.submit(activate_new_license, license_key_input, fingerprint)

        while not future.done():
            parent_window.update()

        parent_window.config(cursor="")
        activation_data, message, error_code = future.result()

        if activation_data:
            save_license_data(activation_data)
            set_license_as_valid()
            messagebox.showinfo("Sucesso", message, parent=parent_window)
            return True, activation_data

        if error_code == "migration_required":
            messagebox.showerror(
                "Licença Incompatível",
                MIGRATION_REQUIRED_MESSAGE,
                parent=parent_window,
            )
            return False, None

        retry = messagebox.askretrycancel(
            "Falha na Ativação",
            f"{message}\nDeseja tentar novamente?",
            parent=parent_window,
        )
        if not retry:
            return False, None
