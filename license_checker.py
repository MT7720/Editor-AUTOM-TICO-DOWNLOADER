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
from datetime import datetime, timezone
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
from security import license_authority
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


MIGRATION_REQUIRED_MESSAGE = (
    "Esta chave de licença utiliza o formato antigo e precisa ser migrada pelo "
    "suporte antes de poder ser utilizada."
)
LEGACY_LICENSE_MIGRATION_URL_ENV_VAR = "EDITOR_AUTOMATICO_LEGACY_MIGRATION_URL"
LEGACY_LICENSE_MIGRATION_TOKEN_ENV_VAR = "EDITOR_AUTOMATICO_LEGACY_MIGRATION_TOKEN"
LEGACY_LICENSE_MIGRATION_TIMEOUT = 10
LICENSE_REVOCATION_FILE_ENV_VAR = "EDITOR_AUTOMATICO_LICENSE_REVOCATIONS"
LICENSE_REVOCATION_CACHE_TTL = 60


_REVOCATION_CACHE: Dict[str, Any] = {
    "serials": set(),
    "path": None,
    "loaded_at": 0.0,
    "mtime": None,
}


def _clear_revocation_cache() -> None:
    _REVOCATION_CACHE.update({
        "serials": set(),
        "path": None,
        "loaded_at": 0.0,
        "mtime": None,
    })


def _load_revocation_serials() -> set[str]:
    path = os.getenv(LICENSE_REVOCATION_FILE_ENV_VAR)
    if not path:
        return set()

    try:
        stat_result = os.stat(path)
    except OSError:
        return set()

    cache_valid = (
        _REVOCATION_CACHE["path"] == path
        and _REVOCATION_CACHE["mtime"] == stat_result.st_mtime
        and (time.monotonic() - _REVOCATION_CACHE["loaded_at"]) < LICENSE_REVOCATION_CACHE_TTL
    )
    if cache_valid:
        return set(_REVOCATION_CACHE["serials"])

    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        payload = {}

    revoked = payload.get("revoked") if isinstance(payload, dict) else None
    serials = {str(value) for value in revoked} if isinstance(revoked, list) else set()

    _REVOCATION_CACHE.update(
        {
            "serials": set(serials),
            "path": path,
            "mtime": stat_result.st_mtime,
            "loaded_at": time.monotonic(),
        }
    )
    return serials


def _parse_claims_timestamp(timestamp: str) -> datetime:
    normalized = timestamp.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return datetime.fromisoformat(normalized).astimezone(timezone.utc)


def _looks_like_compact_token(value: str) -> bool:
    return value.count(".") == 1


def _evaluate_license_token(
    token: str, fingerprint: str
) -> Tuple[Optional[Dict[str, Any]], str, str]:
    """Return (claims, status, detail) for a compact license token."""

    try:
        claims = license_authority.verify_token(token)
    except ValueError as exc:
        return None, "invalid", f"Token de licença inválido: {exc}"

    serial = str(claims.get("serial", "") or "").strip()
    revoked_serials = _load_revocation_serials()
    if serial and serial in revoked_serials:
        return claims, "revoked", "Esta licença foi revogada pelo emissor."

    token_fingerprint = str(claims.get("fingerprint", "") or "").strip()
    if token_fingerprint and token_fingerprint != fingerprint:
        return claims, "fingerprint_mismatch", (
            "O fingerprint associado à licença não corresponde a esta máquina."
        )

    expiry_raw = claims.get("exp") or claims.get("expiry")
    if isinstance(expiry_raw, str):
        try:
            expiry = _parse_claims_timestamp(expiry_raw)
        except ValueError:
            return claims, "invalid", "Data de expiração inválida no token da licença."
        if expiry < datetime.now(timezone.utc):
            return claims, "expired", "A licença encontra-se expirada."

    return claims, "ok", "Licença válida."


def _build_activation_payload(
    token: str, claims: Dict[str, Any], extra_meta: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "valid": True,
        "key": token,
        "serial": claims.get("serial"),
        "seats": claims.get("seats"),
    }
    if extra_meta:
        meta.update(extra_meta)

    return {
        "meta": meta,
        "data": {
            "type": "licenses",
            "id": claims.get("customer_id"),
        },
        "claims": claims,
    }


def _get_delegated_credential(purpose: str) -> Tuple[Optional[str], Optional[str]]:
    token = os.getenv(LEGACY_LICENSE_MIGRATION_TOKEN_ENV_VAR)
    if token:
        return token, None

    try:
        credentials = get_license_service_credentials()
    except RuntimeError as exc:
        return None, str(exc)

    return credentials.product_token, None


def _call_migration_service(
    legacy_key: str, fingerprint: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    url = os.getenv(LEGACY_LICENSE_MIGRATION_URL_ENV_VAR)
    if not url:
        return None, MIGRATION_REQUIRED_MESSAGE

    delegated_token, error = _get_delegated_credential("legacy_migration")
    if not delegated_token:
        detail = (
            f"{MIGRATION_REQUIRED_MESSAGE} {error}".strip()
            if error
            else MIGRATION_REQUIRED_MESSAGE
        )
        return None, detail

    headers = {
        "Authorization": f"Bearer {delegated_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {"licenseKey": legacy_key, "fingerprint": fingerprint}

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=LEGACY_LICENSE_MIGRATION_TIMEOUT,
        )
    except requests.RequestException as exc:
        return None, f"{MIGRATION_REQUIRED_MESSAGE} Erro ao contactar o serviço de migração: {exc}"

    if response.status_code != 200:
        try:
            data = response.json()
        except ValueError:
            data = {}
        if isinstance(data, dict):
            detail = data.get("error") or data.get("message") or data.get("detail")
        else:
            detail = None
        detail_message = detail or f"Serviço de migração respondeu com {response.status_code}."
        return None, f"{MIGRATION_REQUIRED_MESSAGE} Detalhes: {detail_message}"

    try:
        result = response.json()
    except ValueError:
        return None, f"{MIGRATION_REQUIRED_MESSAGE} Resposta inválida do serviço de migração."

    if not isinstance(result, dict) or "token" not in result:
        return None, f"{MIGRATION_REQUIRED_MESSAGE} Resposta do serviço sem token de licença."

    return result, None


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
                data, message, error_code = self._future.result()
            except Exception as exc:  # pragma: no cover - cenário inesperado
                self._handle_failure(f"Erro inesperado durante a ativação: {exc}")
                return

            if data:
                self.result_data = data
                self.result_message = message
                self.destroy()
                return

            failure_message = message or "Falha na ativação da licença."
            if error_code == "migration_required":
                failure_message = (
                    f"{failure_message}\n{MIGRATION_REQUIRED_MESSAGE}"
                    if MIGRATION_REQUIRED_MESSAGE not in failure_message
                    else failure_message
                )
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

def validate_license_with_id(license_id, fingerprint, license_key=None):
    """
    Revalida uma licença existente junto à API do Keygen.

    É efetuada uma requisição ``POST`` para o endpoint de validação remoto,
    enviando a impressão digital da máquina e, quando disponível, a chave da
    licença previamente armazenada. A função devolve sempre uma tupla
    ``(payload, error, invalid_detail)``: ``payload`` contém o JSON devolvido
    pelo serviço quando a comunicação é bem-sucedida (mesmo que a licença seja
    considerada inválida); ``error`` traz uma mensagem normalizada quando ocorre
    algum problema de rede ou quando a resposta não pode ser interpretada; e
    ``invalid_detail`` descreve situações fatais em que a licença deixou de
    existir (por exemplo, quando o serviço responde ``404`` ou "not found").
    """

    if license_key and isinstance(license_key, str) and _looks_like_compact_token(license_key):
        claims, status, detail = _evaluate_license_token(license_key, fingerprint)
        if claims is None and status == "invalid":
            return None, detail, None

        if claims:
            meta: Dict[str, Any] = {
                "valid": status == "ok",
                "key": license_key,
                "serial": claims.get("serial"),
                "seats": claims.get("seats"),
            }
            if status != "ok":
                meta["detail"] = detail

            payload = {
                "meta": meta,
                "data": {
                    "type": "licenses",
                    "id": claims.get("customer_id", license_id),
                },
                "claims": claims,
            }

            return payload, None, None

    try:
        credentials = get_license_service_credentials()
    except RuntimeError as exc:
        return None, str(exc), None

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
        return None, "Não foi possível contactar o servidor de licenças.", None

    if response.status_code >= 400:
        detail = None
        error_code = None
        try:
            error_info = response.json().get("errors", [{}])[0]
            detail = error_info.get("detail")
            error_code = error_info.get("code")
        except (ValueError, AttributeError, IndexError):
            detail = None
            error_code = None

        normalized_detail = (detail or "Licença não encontrada ou removida.").strip()
        lowered_detail = normalized_detail.lower()
        is_license_not_found = False
        if error_code:
            code_lower = str(error_code).lower()
            is_license_not_found = code_lower in {"license_not_found"}
        if not is_license_not_found and response.status_code == 404 and lowered_detail:
            mentions_license = any(term in lowered_detail for term in ("license", "licença", "key", "chave"))
            mentions_absence = any(term in lowered_detail for term in ("not found", "não encontrada", "não encontrado"))
            is_license_not_found = mentions_license and mentions_absence

        if is_license_not_found:
            return None, None, normalized_detail

        message = detail or "Não foi possível validar a licença. O servidor rejeitou a solicitação."
        return None, message, None

    try:
        payload = response.json()
    except ValueError:
        return None, "Resposta inválida do servidor de licenças.", None

    return payload, None, None

def activate_new_license(license_key, fingerprint):
    """Ativa uma licença no formato moderno ou migra chaves antigas automaticamente."""

    normalized_key = (license_key or "").strip()
    normalized_fingerprint = (fingerprint or "").strip()

    if not normalized_key:
        return None, "Informe uma chave de licença válida.", None

    if _looks_like_compact_token(normalized_key):
        claims, status, detail = _evaluate_license_token(normalized_key, normalized_fingerprint)
        if status != "ok" or not claims:
            return None, detail, None

        activation_data = _build_activation_payload(normalized_key, claims)
        return activation_data, "Licença ativada com sucesso.", None

    migration_result, error_message = _call_migration_service(normalized_key, normalized_fingerprint)
    if migration_result is None:
        message = error_message or MIGRATION_REQUIRED_MESSAGE
        if MIGRATION_REQUIRED_MESSAGE not in message:
            message = f"{MIGRATION_REQUIRED_MESSAGE} {message}".strip()
        return None, message, "migration_required"

    token = migration_result.get("token")
    claims, status, detail = _evaluate_license_token(token, normalized_fingerprint)
    if status != "ok" or not claims:
        message = detail
        if MIGRATION_REQUIRED_MESSAGE not in message:
            message = f"{MIGRATION_REQUIRED_MESSAGE} {message}".strip()
        error_code = "migration_required" if status == "invalid" else None
        return None, message, error_code

    extra_meta = {"legacy_key": normalized_key}
    if "serial" in migration_result:
        extra_meta["serial"] = migration_result["serial"]
    if "seats" in migration_result:
        extra_meta["seats"] = migration_result["seats"]

    activation_data = _build_activation_payload(token, claims, extra_meta)
    return activation_data, "Licença migrada com sucesso.", None


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
            validation_result, error, invalid_detail = validate_license_with_id(license_id, fingerprint, license_key)
            if invalid_detail:
                initial_status_messages.append(
                    f"A licença armazenada deixou de ser válida: {invalid_detail}"
                )
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
