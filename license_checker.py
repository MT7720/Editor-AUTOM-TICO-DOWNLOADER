import base64
import binascii
import hashlib
import json
import os
import platform
import re
import secrets
import subprocess
import sys
import time
import tkinter as tk
from tkinter import messagebox
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

import requests
import ttkbootstrap as ttk
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from ttkbootstrap.constants import *

# --- NOVO IMPORT ---
# Importa a função para atualizar o estado da licença
from security.license_manager import set_license_as_valid
from security.secrets import (
    LicenseServiceCredentials,
    SecretLoaderError,
    get_inline_credentials_snapshot,
    load_license_secrets,
    persist_inline_credentials,
)


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

MIGRATION_REQUIRED_MESSAGE = (
    "Esta versão do Editor Automático aceita apenas chaves emitidas diretamente pelo Keygen. "
    "Solicite uma chave actualizada no portal oficial para continuar."
)

PLACEHOLDER_ACCOUNT_ID = "9798e344-f107-4cfd-bcd3-af9b8e75d352"


@lru_cache(maxsize=1)
def get_license_service_credentials() -> LicenseServiceCredentials:
    """Obtém as credenciais do serviço de licenças a partir do canal seguro."""

    return load_license_secrets()


def get_api_base_url() -> str:
    return get_license_service_credentials().api_base_url


def get_product_token() -> str:
    return get_license_service_credentials().product_token


def _validate_key_with_keygen(
    license_key: str, fingerprint: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    """Comunica com a API do Keygen para validar uma chave de licença."""

    normalized_key = (license_key or "").strip()
    normalized_fingerprint = (fingerprint or "").strip()

    if not normalized_key:
        return None, "Informe uma chave de licença válida.", None

    try:
        credentials = get_license_service_credentials()
    except RuntimeError as exc:
        return None, str(exc), None

    headers = {
        "Authorization": f"Bearer {credentials.product_token}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
    }
    payload: Dict[str, Any] = {
        "data": {"type": "licenses"},
        "meta": {"key": normalized_key},
    }
    if normalized_fingerprint:
        payload["meta"]["fingerprint"] = normalized_fingerprint

    try:
        response = requests.post(
            f"{credentials.api_base_url}/licenses/actions/validate-key",
            json=payload,
            headers=headers,
            timeout=10,
        )
    except requests.RequestException:
        return None, "Não foi possível contactar o servidor de licenças.", None

    if response.status_code >= 400:
        detail = None
        error_code = None
        try:
            errors = response.json().get("errors", [])
            if errors:
                detail = errors[0].get("detail")
                error_code = errors[0].get("code")
        except (ValueError, AttributeError, IndexError):
            detail = None
            error_code = None

        normalized_detail = (detail or "Não foi possível validar a licença.").strip()
        lowered_code = str(error_code or "").lower()
        invalid_detail = None
        if lowered_code in {"license_not_found", "license_key_not_found"}:
            invalid_detail = normalized_detail
        elif response.status_code == 404:
            invalid_detail = normalized_detail

        if (
            response.status_code == 404
            and "account" in normalized_detail.lower()
        ):
            guidance = (
                " Verifique o Account ID configurado nas opções avançadas do diálogo de ativação."
            )
            if guidance.strip() not in normalized_detail:
                normalized_detail = f"{normalized_detail}{guidance}"
            invalid_detail = normalized_detail

        return None, normalized_detail, invalid_detail

    try:
        payload = response.json()
    except ValueError:
        return None, "Resposta inválida do servidor de licenças.", None

    meta = payload.setdefault("meta", {})
    meta.setdefault("key", normalized_key)
    if normalized_fingerprint:
        meta.setdefault("fingerprint", normalized_fingerprint)

    return payload, None, None


def extract_license_key(data: Optional[Dict[str, Any]]) -> Optional[str]:
    """Extrai a chave de licença das diferentes estruturas de cache suportadas."""

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

        self._advanced_visible = False
        self._advanced_widgets: list[tk.Widget] = []
        self._build_advanced_section(main_frame)

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

        self._update_status(initial_status, "secondary")

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

    def _update_status(self, message: Optional[str], style: str) -> None:
        cleaned_message = (message or "").strip()
        if not cleaned_message:
            self.status_label.configure(text="", bootstyle="secondary")
            return

        self.status_label.configure(text=cleaned_message, bootstyle=style)

    def _toggle_inputs(self, enabled: bool) -> None:
        state = NORMAL if enabled else DISABLED
        self.entry.configure(state=state)
        self.ok_button.configure(state=state)
        self.cancel_button.configure(state=NORMAL)
        for widget in getattr(self, "_advanced_widgets", []):
            try:
                widget.configure(state=state)
            except tk.TclError:
                continue

    def on_ok(self, event=None):
        if self._future is not None:
            return

        license_key = (self.entry.get() or "").strip()
        if not license_key:
            self._update_status("Informe uma chave de licença para continuar.", "danger")
            return

        if not self._ensure_credentials_saved():
            return

        self._start_activation(license_key)

    def _build_advanced_section(self, parent: tk.Misc) -> None:
        credentials = get_inline_credentials_snapshot()
        account_default = credentials.get("account_id", "")
        product_default = credentials.get("product_token", "")
        api_default = credentials.get("api_base_url", "")

        toggle_container = ttk.Frame(parent)
        toggle_container.pack(fill=X, pady=(0, 6))

        self._advanced_toggle_button = ttk.Button(
            toggle_container,
            text="Mostrar configuração avançada",
            command=self._toggle_advanced_section,
            bootstyle="link",
        )
        self._advanced_toggle_button.pack(anchor=W)

        self.advanced_frame = ttk.Labelframe(
            parent,
            text="Credenciais do Keygen",
            padding=12,
        )
        self.advanced_frame.pack(fill=BOTH, expand=True, pady=(0, 12))
        self.advanced_frame.pack_forget()

        guidance = (
            "Utilize o Account ID e o Product Token fornecidos pelo portal do Keygen. "
            "Valores de exemplo provocam a mensagem 'account not found'."
        )
        warning_label = ttk.Label(
            self.advanced_frame,
            text=guidance,
            wraplength=420,
            bootstyle="warning",
            justify=LEFT,
        )
        warning_label.grid(row=0, column=0, columnspan=2, sticky=W, pady=(0, 10))

        ttk.Label(
            self.advanced_frame,
            text="Account ID (UUID da conta)",
            justify=LEFT,
        ).grid(row=1, column=0, sticky=W)

        self.account_entry = ttk.Entry(self.advanced_frame, width=48)
        self.account_entry.grid(row=1, column=1, sticky=EW, padx=(10, 0))
        if account_default:
            self.account_entry.insert(0, account_default)

        ttk.Label(
            self.advanced_frame,
            text="Product Token",
            justify=LEFT,
        ).grid(row=2, column=0, sticky=W, pady=(8, 0))

        self.product_entry = ttk.Entry(self.advanced_frame, width=48, show="•")
        self.product_entry.grid(row=2, column=1, sticky=EW, padx=(10, 0), pady=(8, 0))
        if product_default:
            self.product_entry.insert(0, product_default)

        self._show_token_var = tk.BooleanVar(value=False)
        self._token_visibility_button = ttk.Checkbutton(
            self.advanced_frame,
            text="Mostrar token",
            variable=self._show_token_var,
            command=self._toggle_product_visibility,
        )
        self._token_visibility_button.grid(row=3, column=1, sticky=W, padx=(10, 0), pady=(2, 0))

        ttk.Label(
            self.advanced_frame,
            text="API Base URL (opcional)",
            justify=LEFT,
        ).grid(row=4, column=0, sticky=W, pady=(8, 0))

        self.api_entry = ttk.Entry(self.advanced_frame, width=48)
        self.api_entry.grid(row=4, column=1, sticky=EW, padx=(10, 0), pady=(8, 0))
        if api_default:
            self.api_entry.insert(0, api_default)

        ttk.Label(
            self.advanced_frame,
            text="Deixe em branco para usar https://api.keygen.sh/v1/accounts/<AccountID>.",
            wraplength=420,
            justify=LEFT,
        ).grid(row=5, column=0, columnspan=2, sticky=W, pady=(6, 0))

        self.advanced_frame.columnconfigure(1, weight=1)

        self._advanced_widgets.extend(
            [
                self._advanced_toggle_button,
                self.account_entry,
                self.product_entry,
                self.api_entry,
                self._token_visibility_button,
            ]
        )

        should_show = not account_default or account_default == PLACEHOLDER_ACCOUNT_ID
        self._set_advanced_visibility(should_show)

    def _toggle_product_visibility(self) -> None:
        show_value = "" if self._show_token_var.get() else "•"
        self.product_entry.configure(show=show_value)

    def _toggle_advanced_section(self) -> None:
        self._set_advanced_visibility(not self._advanced_visible)

    def _set_advanced_visibility(self, visible: bool) -> None:
        if visible == self._advanced_visible:
            return

        self._advanced_visible = visible
        if visible:
            self.advanced_frame.pack(fill=BOTH, expand=True, pady=(0, 12))
            self._advanced_toggle_button.configure(text="Ocultar configuração avançada")
        else:
            self.advanced_frame.pack_forget()
            self._advanced_toggle_button.configure(text="Mostrar configuração avançada")

    def _ensure_credentials_saved(self) -> bool:
        if not hasattr(self, "account_entry"):
            return True

        account_id = (self.account_entry.get() or "").strip()
        product_token = (self.product_entry.get() or "").strip()
        api_base_url = (self.api_entry.get() or "").strip()

        if not account_id and not product_token and not api_base_url:
            return True

        if not account_id or not product_token:
            self._update_status(
                "Informe o Account ID e o Product Token fornecidos pelo Keygen nas opções avançadas.",
                "danger",
            )
            return False

        env_provisioned = any(
            os.getenv(var)
            for var in (
                "KEYGEN_LICENSE_BUNDLE",
                "KEYGEN_LICENSE_BUNDLE_PATH",
                "KEYGEN_ACCOUNT_ID",
                "KEYGEN_PRODUCT_TOKEN",
            )
        )

        if account_id == PLACEHOLDER_ACCOUNT_ID and not env_provisioned:
            self._update_status(
                "Substitua o Account ID de exemplo pelo valor real disponibilizado pelo Keygen.",
                "danger",
            )
            return False

        try:
            persist_inline_credentials(account_id, product_token, api_base_url or None)
        except SecretLoaderError as exc:
            self._update_status(str(exc), "danger")
            return False

        if hasattr(get_license_service_credentials, "cache_clear"):
            get_license_service_credentials.cache_clear()

        return True

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
                data, message, detail = self._future.result()
            except Exception as exc:  # pragma: no cover - cenário inesperado
                self._handle_failure(f"Erro inesperado durante a ativação: {exc}")
                return

            if data:
                self.result_data = data
                self.result_message = message
                self.destroy()
                return

            failure_message = message or "Falha na ativação da licença."
            if detail and detail not in failure_message:
                failure_message = f"{failure_message}\n{detail}"
            self._handle_failure(failure_message)
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

def _looks_like_legacy_key(license_key: str) -> bool:
    """Detecta tokens legados emitidos pelo fluxo offline anterior."""

    return "." in license_key


def validate_license_key(
    license_key: Optional[str], fingerprint: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    """Valida uma chave de licença diretamente no Keygen."""

    normalized_key = (license_key or "").strip()
    if not normalized_key:
        return None, "Informe uma chave de licença válida.", None

    if _looks_like_legacy_key(normalized_key):
        return None, MIGRATION_REQUIRED_MESSAGE, "migration_required"

    return _validate_key_with_keygen(normalized_key, fingerprint)


def validate_license_with_id(license_id, fingerprint, license_key=None):
    """Compatibilidade retroativa: ignora o ID e valida apenas pela chave."""

    return validate_license_key(license_key, fingerprint)

def activate_new_license(license_key, fingerprint):
    """Solicita a validação da chave diretamente à API do Keygen."""

    payload, error, invalid_detail = validate_license_key(license_key, fingerprint)
    if payload:
        meta = payload.setdefault("meta", {})
        meta.setdefault("valid", True)
        return payload, "Licença ativada com sucesso.", None

    return payload, error, invalid_detail


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
        license_key = extract_license_key(stored_data)
        if license_key:
            validation_result, error, invalid_detail = validate_license_key(license_key, fingerprint)
            if invalid_detail:
                detail_message = invalid_detail
                if invalid_detail == "migration_required":
                    detail_message = MIGRATION_REQUIRED_MESSAGE
                initial_status_messages.append(
                    f"A licença armazenada deixou de ser válida: {detail_message}"
                )
            elif error:
                initial_status_messages.append(
                    f"Não foi possível revalidar a licença existente: {error}"
                )
            elif validation_result and validation_result.get("meta", {}).get("valid"):
                set_license_as_valid()
                return True, validation_result
        else:
            initial_status_messages.append(
                "Os dados locais de licença não possuem a chave necessária para revalidação."
            )

    try:
        load_license_secrets()
    except SecretLoaderError as exc:
        diagnostic = (
            "Credenciais do serviço de licenças ausentes. "
            "O instalador oficial injeta KEYGEN_LICENSE_BUNDLE automaticamente; "
            "verifique se o pacote foi construído com o bundle autenticado."
        )
        print("Diagnóstico de licenciamento: " + diagnostic)
        print(f"Detalhes técnicos: {exc}")
        initial_status_messages.append(
            "As credenciais do serviço de licenças não estão disponíveis nesta instalação. "
            "Peça um novo instalador ou contacte o suporte antes de tentar ativar novamente."
        )

    if initial_status_messages:
        print("Mensagens iniciais de status da licença:")
        for message in initial_status_messages:
            print(f"- {message}")

    dialog = CustomLicenseDialog(
        parent_window,
        fingerprint,
        activation_timeout=activation_timeout,
        initial_status=None,
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
