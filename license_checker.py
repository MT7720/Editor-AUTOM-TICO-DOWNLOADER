import base64
import json
import os
import secrets
import sys
import hashlib
import logging
import platform
import subprocess
from functools import lru_cache
from typing import Any, Dict, Optional

import requests
import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as ttk
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

ACCOUNT_ID = "9798e344-f107-4cfd-bc83-af9b8e75d352"
PRODUCT_TOKEN_ENV_VAR = "KEYGEN_PRODUCT_TOKEN"
PRODUCT_TOKEN_FILE_ENV_VAR = "KEYGEN_PRODUCT_TOKEN_FILE"
API_BASE_URL = f"https://api.keygen.sh/v1/accounts/{ACCOUNT_ID}"
ICON_FILE = resource_path("icone.ico")

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


class LicenseTamperedError(RuntimeError):
    """Raised when the persisted license payload fails integrity checks."""


def _load_secret_from_file(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as secret_file:
            content = secret_file.read().strip()
            return content or None
    except OSError:
        return None


@lru_cache(maxsize=1)
def get_product_token() -> str:
    token = os.getenv(PRODUCT_TOKEN_ENV_VAR)
    if token:
        return token.strip()

    secret_file = os.getenv(PRODUCT_TOKEN_FILE_ENV_VAR)
    if secret_file:
        file_token = _load_secret_from_file(secret_file)
        if file_token:
            return file_token

    raise RuntimeError(
        "A variável de ambiente 'KEYGEN_PRODUCT_TOKEN' (ou ficheiro apontado por "
        "'KEYGEN_PRODUCT_TOKEN_FILE') deve estar definida antes de utilizar a "
        "validação de licenças."
    )


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

def get_machine_fingerprint():
    # ... (O conteúdo desta função não muda)
    identifier = None
    if platform.system() == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            winreg.CloseKey(key)
            identifier = value
        except Exception: pass
    if not identifier and platform.system() == "Windows":
        try:
            output = subprocess.check_output("wmic csproduct get uuid", shell=True, text=True, stderr=subprocess.DEVNULL)
            value = output.split('\n')[1].strip()
            if len(value) > 5: identifier = value
        except Exception: pass
    if not identifier:
        identifier = f"{platform.system()}-{platform.node()}-{platform.machine()}"
    return hashlib.sha256(identifier.encode()).hexdigest()

def validate_license_with_id(license_id, fingerprint):
    # ... (O conteúdo desta função não muda)
    token = get_product_token()
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.api+json"}
    try:
        response = requests.post(f"{API_BASE_URL}/licenses/{license_id}/actions/validate", params={"fingerprint": fingerprint}, headers=headers)
        return response.json()
    except Exception: return None

def activate_new_license(license_key, fingerprint):
    # ... (O conteúdo desta função não muda)
    headers = {"Content-Type": "application/vnd.api+json", "Accept": "application/vnd.api+json"}
    payload = {"meta": {"key": license_key}}
    try:
        r = requests.post(f"{API_BASE_URL}/licenses/actions/validate-key", json=payload, headers=headers)
        r.raise_for_status()
        validation_data = r.json()
        if not validation_data.get("meta", {}).get("valid"):
            return None, validation_data.get("meta", {}).get("detail", "Chave inválida ou expirada.")
        license_id = validation_data["data"]["id"]
    except requests.exceptions.RequestException:
        return None, "Não foi possível contactar o servidor para validar a chave."

    activation_payload = {"data": {"type": "machines", "attributes": {"fingerprint": fingerprint}, "relationships": {"license": {"data": {"type": "licenses", "id": license_id}}}}}
    try:
        token = get_product_token()
        r = requests.post(f"{API_BASE_URL}/machines", json=activation_payload, headers={"Authorization": f"Bearer {token}", **headers})
        r.raise_for_status()
        return validation_data, "Ativação bem-sucedida."
    except requests.exceptions.RequestException as e:
        if e.response and e.response.status_code == 422 and e.response.json().get('errors', [{}])[0].get('code') == 'FINGERPRINT_ALREADY_TAKEN':
            return validation_data, "Máquina já estava ativada."
        return None, "Não foi possível ativar esta máquina. A licença pode estar em uso."

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

    if stored_data:
        license_id = stored_data.get("data", {}).get("id")
        if license_id:
            validation_result = validate_license_with_id(license_id, fingerprint)
            if validation_result and validation_result.get("meta", {}).get("valid"):
                return True, validation_result
    
    # REMOVIDO: A criação e destruição da janela temporária foi removida.

    while True:
        # Usa a janela principal (escondida) como pai para o diálogo.
        dialog = CustomLicenseDialog(parent_window)
        license_key_input = dialog.result
        
        if not license_key_input:
            messagebox.showwarning("Ativação Necessária", "É necessária uma chave de licença para usar este programa.", parent=parent_window)
            return False, None
        
        activation_data, message = activate_new_license(license_key_input, fingerprint)
        if activation_data:
            messagebox.showinfo("Sucesso", "A sua licença foi ativada com sucesso nesta máquina!", parent=parent_window)
            save_license_data(activation_data, fingerprint)
            return True, activation_data
        else:
            if not messagebox.askretrycancel("Falha na Ativação", f"{message}\nDeseja tentar novamente?", parent=parent_window):
                return False, None
