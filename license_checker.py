import base64
import binascii
import hashlib
import json
import os
import platform
import secrets
import subprocess
import sys
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from tkinter import messagebox

import requests
import ttkbootstrap as ttk
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from ttkbootstrap.constants import *

# --- NOVO IMPORT ---
# Importa a função para atualizar o estado da licença
from security.license_manager import set_license_as_valid
from security.secrets import LicenseServiceCredentials, SecretLoaderError, load_license_secrets


class LicenseTamperedError(Exception):
    """Sinaliza que o ficheiro de licença foi adulterado ou corrompido."""


def _derive_encryption_key(fingerprint: str) -> bytes:
    """Deriva uma chave simétrica a partir do fingerprint da máquina."""

    return hashlib.sha256(fingerprint.encode()).digest()
# --------------------


def resource_path(relative_path):
    """ Obtém o caminho absoluto para o recurso, funciona para dev e para PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

ICON_FILE = resource_path("icone.ico")
_EXECUTOR = ThreadPoolExecutor(max_workers=2)


@lru_cache(maxsize=1)
def get_license_service_credentials() -> LicenseServiceCredentials:
    """Obtém as credenciais do serviço de licenças a partir do canal seguro."""

    try:
        return load_license_secrets()
    except SecretLoaderError as exc:
        raise RuntimeError(
            "Não foi possível carregar as credenciais do serviço de licenças. "
            "Certifique-se de que o bundle seguro foi provisionado pelo broker. "
            f"Detalhes: {exc}"
        ) from exc


def get_api_base_url() -> str:
    return get_license_service_credentials().api_base_url


def get_product_token() -> str:
    return get_license_service_credentials().product_token

class CustomLicenseDialog(ttk.Toplevel):
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
        ttk.Frame(button_frame).pack(side=LEFT, expand=True)
        cancel_button = ttk.Button(button_frame, text="Cancelar", width=10, command=self.on_cancel, bootstyle="secondary")
        cancel_button.pack(side=RIGHT, padx=(10, 0))
        ok_button = ttk.Button(button_frame, text="Ativar", width=10, command=self.on_ok, bootstyle="success")
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

def get_app_data_path():
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

def get_machine_fingerprint():
    identifier = None
    if platform.system() == "Windows":
        try:
            output = subprocess.check_output("wmic csproduct get uuid", shell=True, text=True, stderr=subprocess.DEVNULL)
            value = output.split('\n')[1].strip()
            if len(value) > 5: identifier = value
        except Exception: pass
    if not identifier:
        identifier = f"{platform.system()}-{platform.node()}-{platform.machine()}"
    return hashlib.sha256(identifier.encode()).hexdigest()

def validate_license_with_id(license_id, fingerprint, license_key=None):
    """
    Revalida uma licença existente junto à API do Keygen.

    É efetuada uma requisição ``POST`` para o endpoint de validação remoto,
    enviando a impressão digital da máquina e, quando disponível, a chave da
    licença previamente armazenada. A função devolve sempre uma tupla
    ``(payload, error)``: ``payload`` contém o JSON devolvido pelo serviço
    quando a comunicação é bem-sucedida (mesmo que a licença seja considerada
    inválida) e ``error`` traz uma mensagem normalizada quando ocorre algum
    problema de rede ou quando a resposta não pode ser interpretada.
    """

    try:
        credentials = get_license_service_credentials()
    except RuntimeError as exc:
        return None, str(exc)

    headers = {
        "Authorization": f"Bearer {credentials.product_token}",
        "Accept": "application/vnd.api+json",
    }
    params = {"fingerprint": fingerprint}
    if license_key:
        params["key"] = license_key

    try:
        response = requests.post(
            f"{credentials.api_base_url}/licenses/{license_id}/actions/validate",
            params=params,
            headers=headers,
            timeout=10,
        )
    except requests.exceptions.RequestException:
        return None, "Não foi possível contactar o servidor de licenças."

    if response.status_code >= 400:
        detail = None
        try:
            detail = response.json().get("errors", [{}])[0].get("detail")
        except (ValueError, AttributeError, IndexError):
            detail = None
        message = detail or "Não foi possível validar a licença. O servidor rejeitou a solicitação."
        return None, message

    try:
        payload = response.json()
    except ValueError:
        return None, "Resposta inválida do servidor de licenças."

    return payload, None

def activate_new_license(license_key, fingerprint):
    """ Ativa uma nova licença usando o fluxo simples e funcional do script antigo. """
    try:
        credentials = get_license_service_credentials()
    except RuntimeError as exc:
        return None, str(exc)

    product_token = credentials.product_token
    headers = {
        "Content-Type": "application/vnd.api+json",
        "Accept": "application/vnd.api+json",
    }
    payload = {"meta": {"key": license_key}}
    try:
        r = requests.post(
            f"{credentials.api_base_url}/licenses/actions/validate-key",
            json=payload,
            headers=headers,
        )
        r.raise_for_status()
        validation_data = r.json()
        if not validation_data.get("meta", {}).get("valid"):
            return None, validation_data.get("meta", {}).get("detail", "Chave inválida ou expirada.")
        license_id = validation_data["data"]["id"]
    except requests.exceptions.RequestException:
        return None, "Não foi possível contactar o servidor para validar a chave."

    activation_payload = {
        "data": {
            "type": "machines",
            "attributes": {"fingerprint": fingerprint},
            "relationships": {"license": {"data": {"type": "licenses", "id": license_id}}}
        }
    }
    auth_headers = {"Authorization": f"Bearer {product_token}", **headers}
    try:
        r = requests.post(
            f"{credentials.api_base_url}/machines",
            json=activation_payload,
            headers=auth_headers,
        )
        r.raise_for_status()
        # Retorna os dados da validação original para serem salvos, como no script antigo
        return validation_data, "Ativação bem-sucedida."
    except requests.exceptions.RequestException as e:
        if e.response and e.response.status_code == 422:
            error_detail = e.response.json().get('errors', [{}])[0]
            if error_detail.get('code') == 'FINGERPRINT_ALREADY_TAKEN':
                return validation_data, "Máquina já estava ativada."
        return None, "Não foi possível ativar esta máquina. A licença pode estar em uso ou sem vagas."


def save_license_data(license_data, fingerprint):
    try:
        key = _derive_encryption_key(fingerprint)
        nonce = secrets.token_bytes(12)
        aes = AESGCM(key)
        plaintext = json.dumps(license_data).encode("utf-8")
        ciphertext = aes.encrypt(nonce, plaintext, None)
        payload = {
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }
        with open(LICENSE_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception:
        messagebox.showerror(
            "Erro ao Guardar",
            f"Não foi possível guardar o ficheiro de licença em:\n{LICENSE_FILE_PATH}",
        )


def load_license_data(fingerprint):
    if not os.path.exists(LICENSE_FILE_PATH):
        return None

    try:
        with open(LICENSE_FILE_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except OSError:
        return None
    except json.JSONDecodeError as exc:
        raise LicenseTamperedError("Formato do ficheiro de licença inválido.") from exc

    try:
        nonce_b64 = payload["nonce"]
        ciphertext_b64 = payload["ciphertext"]
        nonce = base64.b64decode(nonce_b64)
        ciphertext = base64.b64decode(ciphertext_b64)
        key = _derive_encryption_key(fingerprint)
        aes = AESGCM(key)
        plaintext = aes.decrypt(nonce, ciphertext, None)
        return json.loads(plaintext.decode("utf-8"))
    except (KeyError, binascii.Error, InvalidTag, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise LicenseTamperedError("Os dados de licença guardados foram adulterados.") from exc

def _set_wait_state(window, enabled):
    """Atualiza o cursor e o estado de interação da janela principal."""
    try:
        window.config(cursor="watch" if enabled else "")
    except tk.TclError:
        pass

    try:
        window.attributes("-disabled", enabled)
    except tk.TclError:
        # Nem todas as plataformas suportam esta flag; ignoramos silenciosamente.
        pass

    window.update_idletasks()


def check_license(parent_window, activation_timeout=15):
    """
    Função principal corrigida.
    1. Tenta carregar a licença do cache.
    2. Se encontrar, REVALIDA online para garantir que ainda é válida.
    3. Se não houver cache ou a revalidação falhar, pede uma nova ativação.
    """
    fingerprint = get_machine_fingerprint()
    try:
        stored_data = load_license_data(fingerprint)
    except LicenseTamperedError:
        messagebox.showwarning(
            "Licença inválida",
            "Os dados de licença guardados foram adulterados e precisarão de reativação.",
            parent=parent_window,
        )
        stored_data = None

    if stored_data:
        license_id = stored_data.get("data", {}).get("id")
        license_key = stored_data.get("meta", {}).get("key") if isinstance(stored_data, dict) else None
        if license_id:
            # CORREÇÃO: Sempre revalida a licença do cache online
            validation_result, error = validate_license_with_id(license_id, fingerprint, license_key)
            if error:
                messagebox.showwarning(
                    "Falha na Validação",
                    f"Não foi possível validar a licença guardada:\n{error}",
                    parent=parent_window,
                )
            elif validation_result and validation_result.get("meta", {}).get("valid"):
                print("Licença em cache revalidada online com sucesso.")

                # <<< --- CORREÇÃO 1 --- >>>
                # Atualiza o estado global para VÁLIDO
                set_license_as_valid()
                # <<< ------------------ >>>

                return True, validation_result # Retorna os dados de validação atualizados
    
    # Se não há licença válida no cache, inicia o processo de ativação
    while True:
        dialog = CustomLicenseDialog(parent_window)
        license_key_input = (dialog.result or "").strip()
        
        if not license_key_input:
            messagebox.showwarning("Ativação Necessária", "É necessária uma chave de licença para usar este programa.", parent=parent_window)
            return False, None
        
        wait_var = tk.BooleanVar(master=parent_window, value=False)
        wait_state = {"data": None, "message": None, "cancelled": False}

        _set_wait_state(parent_window, True)
        future = _EXECUTOR.submit(activate_new_license, license_key_input, fingerprint)
        start_time = time.monotonic()
        timeout_notified = False

        def conclude(result_data=None, result_message=None, cancelled=False):
            if wait_var.get():
                return

            wait_state["data"] = result_data
            wait_state["message"] = result_message
            wait_state["cancelled"] = cancelled
            _set_wait_state(parent_window, False)
            wait_var.set(True)

        def poll_future():
            nonlocal timeout_notified

            if wait_var.get():
                return

            if future.done():
                try:
                    result_data, result_message = future.result()
                except Exception as exc:
                    result_data, result_message = None, f"Erro inesperado durante a ativação: {exc}"
                conclude(result_data, result_message, cancelled=False)
                return

            if activation_timeout and not timeout_notified:
                elapsed = time.monotonic() - start_time
                if elapsed >= activation_timeout:
                    _set_wait_state(parent_window, False)
                    should_continue = messagebox.askretrycancel(
                        "Ativação demorada",
                        "A ativação está a demorar mais do que o esperado.\n"
                        "Verifique a sua ligação e escolha 'Tentar novamente' para continuar a aguardar ou 'Cancelar' para interromper.",
                        parent=parent_window,
                    )

                    if not should_continue:
                        if not future.done():
                            future.cancel()
                        conclude(None, "Ativação cancelada pelo utilizador após tempo limite.", cancelled=True)
                        return

                    timeout_notified = True
                    _set_wait_state(parent_window, True)

            parent_window.after(150, poll_future)

        parent_window.after(150, poll_future)
        parent_window.wait_variable(wait_var)

        if wait_state["cancelled"]:
            messagebox.showinfo("Ativação cancelada", wait_state["message"], parent=parent_window)
            return False, None

        activation_data = wait_state["data"]
        message = wait_state["message"]

        if activation_data:
            # O formato salvo é o mesmo do script antigo, garantindo consistência
            save_license_data(activation_data, fingerprint)
            
            # <<< --- CORREÇÃO 2 --- >>>
            # Atualiza o estado global para VÁLIDO após nova ativação
            set_license_as_valid()
            # <<< ------------------ >>>

            messagebox.showinfo("Sucesso", message, parent=parent_window)
            return True, activation_data
        else:
            if not messagebox.askretrycancel("Falha na Ativação", f"{message}\nDeseja tentar novamente?", parent=parent_window):
                return False, None