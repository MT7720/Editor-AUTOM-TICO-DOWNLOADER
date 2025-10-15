import hashlib
import json
import os
import platform
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional, Tuple

import requests
import tkinter as tk
import ttkbootstrap as ttk
from tkinter import messagebox
from ttkbootstrap.constants import *

from security.license_manager import set_license_as_valid


ACCOUNT_ID = "9798e344-f107-4cfd-bc83-af9b8e75d352"
PRODUCT_TOKEN = "prod-e3d63a2e5b9b825ec166c0bd631be99c5e9cd27761b3f899a3a4014f537e64bdv3"
API_BASE_URL = f"https://api.keygen.sh/v1/accounts/{ACCOUNT_ID}"


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
    def __init__(self, parent: tk.Misc):
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


def validate_license_with_id(license_id: str, fingerprint: str) -> Optional[Dict[str, Any]]:
    headers = {
        "Authorization": f"Bearer {PRODUCT_TOKEN}",
        "Accept": "application/vnd.api+json",
    }
    try:
        response = requests.post(
            f"{API_BASE_URL}/licenses/{license_id}/actions/validate",
            params={"fingerprint": fingerprint},
            headers=headers,
            timeout=10,
        )
    except requests.RequestException:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _request_key_validation(license_key: str, fingerprint: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    headers = {
        "Content-Type": "application/vnd.api+json",
        "Accept": "application/vnd.api+json",
    }
    payload: Dict[str, Any] = {"meta": {"key": license_key}}
    if fingerprint:
        payload["meta"]["fingerprint"] = fingerprint
    try:
        response = requests.post(
            f"{API_BASE_URL}/licenses/actions/validate-key",
            json=payload,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException:
        return None, "Não foi possível contactar o servidor para validar a chave."
    try:
        data = response.json()
    except ValueError:
        return None, "Resposta inválida do servidor de licenças."
    if not data.get("meta", {}).get("valid"):
        detail = data.get("meta", {}).get("detail") or "Chave inválida ou expirada."
        return data, detail
    return data, None


def activate_new_license(license_key: str, fingerprint: str) -> Tuple[Optional[Dict[str, Any]], str]:
    validation_data, error = _request_key_validation(license_key, fingerprint)
    if error:
        return None, error
    if not validation_data:
        return None, "Não foi possível validar a chave de licença."
    license_id = validation_data["data"]["id"]
    activation_payload = {
        "data": {
            "type": "machines",
            "attributes": {"fingerprint": fingerprint},
            "relationships": {"license": {"data": {"type": "licenses", "id": license_id}}},
        }
    }
    headers = {
        "Authorization": f"Bearer {PRODUCT_TOKEN}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
    }
    try:
        response = requests.post(
            f"{API_BASE_URL}/machines",
            json=activation_payload,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        if getattr(exc, "response", None) is not None and exc.response.status_code == 422:
            try:
                error_detail = exc.response.json().get("errors", [{}])[0]
            except ValueError:
                error_detail = {}
            if error_detail.get("code") == "FINGERPRINT_ALREADY_TAKEN":
                return validation_data, "Máquina já estava ativada."
        return None, "Não foi possível ativar esta máquina. A licença pode estar em uso ou sem vagas."
    return validation_data, "Ativação bem-sucedida."


def validate_license_key(
    license_key: Optional[str], fingerprint: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    normalized_key = (license_key or "").strip()
    if not normalized_key:
        return None, "Informe uma chave de licença válida.", "Informe uma chave de licença válida."
    data, error = _request_key_validation(normalized_key, fingerprint)
    if error:
        return data, error, error
    return data, None, None


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
    stored_data = load_license_data()

    if stored_data:
        license_id = stored_data.get("data", {}).get("id")
        if license_id:
            validation_result = validate_license_with_id(license_id, fingerprint)
            if validation_result and validation_result.get("meta", {}).get("valid"):
                set_license_as_valid()
                return True, validation_result

    while True:
        dialog = CustomLicenseDialog(parent_window)
        license_key_input = (dialog.result or "").strip()

        if not license_key_input:
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
        activation_data, message = future.result()

        if activation_data:
            save_license_data(activation_data)
            set_license_as_valid()
            messagebox.showinfo("Sucesso", message, parent=parent_window)
            return True, activation_data

        retry = messagebox.askretrycancel(
            "Falha na Ativação",
            f"{message}\nDeseja tentar novamente?",
            parent=parent_window,
        )
        if not retry:
            return False, None
