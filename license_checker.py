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
from typing import Optional

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

    return load_license_secrets()


def get_api_base_url() -> str:
    return get_license_service_credentials().api_base_url


def get_product_token() -> str:
    return get_license_service_credentials().product_token

class CustomLicenseDialog(ttk.Toplevel):
    """Janela modal responsável por recolher a chave e ativar a licença."""

    def __init__(
        self,
        parent: tk.Misc,
        fingerprint: str,
        activation_timeout: Optional[int] = None,
        initial_status: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        self.transient(parent)
        self.title("Ativação de Licença")
        self.resizable(False, False)
        self.result_data = None
        self.result_message = None
        self.cancelled = False
        self._fingerprint = fingerprint
        self._activation_timeout = activation_timeout
        self._future = None
        self._timeout_notified = False
        self._start_time = None

        try:
            self.iconbitmap(ICON_FILE)
        except tk.TclError:
            print(f"Aviso: Não foi possível carregar o ícone: {ICON_FILE}")

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
            text="Introduza a sua chave de licença para validar o acesso.",
            font=("Segoe UI", 10),
        )
        info_label.pack(pady=(0, 15))

        self.entry = ttk.Entry(main_frame, width=50, font=("Segoe UI", 10))
        self.entry.pack(pady=(0, 12), ipady=4)
        self.entry.focus_set()

        self.status_label = ttk.Label(
            main_frame,
            text="",
            font=("Segoe UI", 9),
            wraplength=420,
            justify=LEFT,
        )
        self.status_label.pack(fill=X, pady=(0, 10))

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x")
        ttk.Frame(button_frame).pack(side=LEFT, expand=True)

        self.cancel_button = ttk.Button(
            button_frame,
            text="Cancelar",
            width=10,
            command=self.on_cancel,
            bootstyle="secondary",
        )
        self.cancel_button.pack(side=RIGHT, padx=(10, 0))

        self.ok_button = ttk.Button(
            button_frame,
            text="Ativar",
            width=10,
            command=self.on_ok,
            bootstyle="success",
        )
        self.ok_button.pack(side=RIGHT)

        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.bind("<Return>", self.on_ok)
        self.bind("<Escape>", self.on_cancel)

        self._update_status(initial_status or "", "secondary")

        parent_state = None
        parent_was_withdrawn = False
        parent_was_iconified = False
        if isinstance(parent, tk.Tk) or isinstance(parent, tk.Toplevel):
            try:
                parent_state = parent.state()
            except tk.TclError:
                parent_state = None

            if parent_state == "withdrawn":
                parent.deiconify()
                parent_was_withdrawn = True
            elif parent_state == "iconic":
                parent.deiconify()
                parent_was_iconified = True

            parent.update_idletasks()

        self.update_idletasks()
        dialog_w, dialog_h = self.winfo_width(), self.winfo_height()
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        x = max((screen_w - dialog_w) // 2, 0)
        y = max((screen_h - dialog_h) // 2, 0)
        self.geometry(f"+{x}+{y}")

        if isinstance(parent, tk.Tk) or isinstance(parent, tk.Toplevel):
            if parent_was_withdrawn:
                parent.withdraw()
            elif parent_was_iconified:
                parent.iconify()
        self.grab_set()
        self.wait_window(self)

    def _update_status(self, message: str, style: str) -> None:
        self.status_label.configure(text=message, bootstyle=style)

    def _toggle_inputs(self, enabled: bool) -> None:
        state = NORMAL if enabled else DISABLED
        self.entry.configure(state=state)
        self.ok_button.configure(state=state)
        self.cancel_button.configure(state=NORMAL)

    def on_ok(self, event=None):
        if self._future is not None:
            return

        license_key = (self.entry.get() or "").strip()
        if not license_key:
            self._update_status("Informe uma chave de licença para continuar.", "danger")
            return

        self._start_activation(license_key)

    def _start_activation(self, license_key: str) -> None:
        self._toggle_inputs(False)
        self._update_status("A contactar o serviço de licenças...", "info")
        self._future = _EXECUTOR.submit(activate_new_license, license_key, self._fingerprint)
        self._start_time = time.monotonic()
        self.after(150, self._poll_future)

    def _poll_future(self) -> None:
        if self._future is None:
            return

        if self._future.done():
            try:
                data, message = self._future.result()
            except Exception as exc:  # pragma: no cover - cenário inesperado
                self._handle_failure(f"Erro inesperado durante a ativação: {exc}")
                return

            if data:
                self.result_data = data
                self.result_message = message
                self.destroy()
                return

            self._handle_failure(message or "Falha na ativação da licença.")
            return

        if (
            self._activation_timeout
            and not self._timeout_notified
            and self._start_time is not None
            and (time.monotonic() - self._start_time) >= self._activation_timeout
        ):
            self._timeout_notified = True
            self._update_status(
                "A ativação está a demorar mais do que o esperado. Verifique a ligação e aguarde mais alguns instantes.",
                "warning",
            )

        self.after(150, self._poll_future)

    def _handle_failure(self, message: str) -> None:
        self._future = None
        self._timeout_notified = False
        self._toggle_inputs(True)
        self._update_status(message, "danger")

    def on_cancel(self, event=None):
        if self._future is not None and not self._future.done():
            self._future.cancel()
        self.cancelled = True
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
    ``(payload, error, invalidated)``: ``payload`` contém o JSON devolvido pelo
    serviço quando a comunicação é bem-sucedida (mesmo que a licença seja
    considerada inválida), ``error`` traz uma mensagem normalizada quando ocorre
    algum problema de rede ou quando a resposta não pode ser interpretada e
    ``invalidated`` assinala quando o servidor indica que a licença é
    definitivamente inválida (por exemplo, foi removida ou não existe).
    """

    try:
        credentials = get_license_service_credentials()
    except RuntimeError as exc:
        return None, str(exc), False

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
        return None, "Não foi possível contactar o servidor de licenças.", False

    invalidated = False

    if response.status_code >= 400:
        detail = None
        try:
            detail = response.json().get("errors", [{}])[0].get("detail")
        except (ValueError, AttributeError, IndexError):
            detail = None

        not_found = response.status_code == 404
        if detail:
            normalized = detail.lower()
            not_found = not_found or "not found" in normalized or "não encontrada" in normalized

        if not_found:
            invalidated = True
            message = detail or "A licença não foi encontrada ou foi removida."
            payload = {"meta": {"valid": False, "detail": message}}
            return payload, None, invalidated

        message = detail or "Não foi possível validar a licença. O servidor rejeitou a solicitação."
        return None, message, invalidated

    try:
        payload = response.json()
    except ValueError:
        return None, "Resposta inválida do servidor de licenças.", False

    return payload, None, invalidated

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
    except Exception as exc:  # pragma: no cover - erro inesperado de IO
        raise RuntimeError(
            f"Não foi possível guardar o ficheiro de licença em: {LICENSE_FILE_PATH}"
        ) from exc


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

def check_license(parent_window, activation_timeout=15):
    """
    Função principal corrigida.
    1. Tenta carregar a licença do cache.
    2. Se encontrar, REVALIDA online para garantir que ainda é válida.
    3. Se não houver cache ou a revalidação falhar, pede uma nova ativação.
    """
    fingerprint = get_machine_fingerprint()
    initial_status_messages: list[str] = []

    try:
        stored_data = load_license_data(fingerprint)
    except LicenseTamperedError:
        print("Aviso: os dados de licença existentes estavam corrompidos; será necessária nova ativação.")
        stored_data = None
        initial_status_messages.append(
            "A licença guardada não pôde ser lida e será necessário introduzir uma nova chave."
        )

    if stored_data:
        license_id = stored_data.get("data", {}).get("id")
        license_key = stored_data.get("meta", {}).get("key") if isinstance(stored_data, dict) else None
        if license_id:
            validation_result, error, invalidated = validate_license_with_id(license_id, fingerprint, license_key)
            if invalidated:
                detail = None
                if isinstance(validation_result, dict):
                    detail = validation_result.get("meta", {}).get("detail")
                detail = detail or "A licença associada a esta instalação já não está disponível."
                initial_status_messages.append(detail)
            elif error:
                initial_status_messages.append(
                    f"Não foi possível revalidar a licença existente: {error}"
                )
            elif validation_result and validation_result.get("meta", {}).get("valid"):
                set_license_as_valid()
                return True, validation_result

    try:
        load_license_secrets()
    except SecretLoaderError as exc:
        print(f"Aviso: não foi possível carregar as credenciais do serviço de licenças: {exc}")
        initial_status_messages.append(
            "As credenciais do serviço de licenças não estão disponíveis. "
            "Confirme a instalação do bundle seguro (detalhes abaixo)."
        )
        initial_status_messages.append(str(exc))

    dialog = CustomLicenseDialog(
        parent_window,
        fingerprint,
        activation_timeout=activation_timeout,
        initial_status="\n".join(initial_status_messages) if initial_status_messages else None,
    )

    if dialog.cancelled or not dialog.result_data:
        return False, None

    activation_data = dialog.result_data

    try:
        save_license_data(activation_data, fingerprint)
    except RuntimeError as exc:
        print(exc)
        return False, None

    set_license_as_valid()
    return True, activation_data
