import os
import sys
import requests
import hashlib
import platform
import subprocess
import tkinter as tk
from tkinter import messagebox
import json
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from concurrent.futures import ThreadPoolExecutor

# --- NOVO IMPORT ---
# Importa a função para atualizar o estado da licença
from security.license_manager import set_license_as_valid
# --------------------


def resource_path(relative_path):
    """ Obtém o caminho absoluto para o recurso, funciona para dev e para PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- CONFIGURAÇÃO CORRIGIDA (BASEADA NO SCRIPT ANTIGO E FUNCIONAL) ---
# Usando o PRODUCT_TOKEN que tem as permissões corretas para validar e ativar.
ACCOUNT_ID = "9798e344-f107-4cfd-bc83-af9b8e75d352" # ID da conta do script antigo
PRODUCT_TOKEN = "prod-e3d63a2e5b9b825ec166c0bd631be99c5e9cd27761b3f899a3a4014f537e64bdv3" # Token do script antigo
API_BASE_URL = f"https://api.keygen.sh/v1/accounts/{ACCOUNT_ID}"
# --------------------------------------------------------------------

ICON_FILE = resource_path("icone.ico")
_EXECUTOR = ThreadPoolExecutor(max_workers=2)

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

def validate_license_with_id(license_id, fingerprint):
    """ Revalida uma licença existente online (do script antigo). """
    headers = {"Authorization": f"Bearer {PRODUCT_TOKEN}", "Accept": "application/vnd.api+json"}
    try:
        response = requests.post(
            f"{API_BASE_URL}/licenses/{license_id}/actions/validate",
            params={"fingerprint": fingerprint},
            headers=headers
        )
        return response.json()
    except requests.exceptions.RequestException:
        return None

def activate_new_license(license_key, fingerprint):
    """ Ativa uma nova licença usando o fluxo simples e funcional do script antigo. """
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

    activation_payload = {
        "data": {
            "type": "machines",
            "attributes": {"fingerprint": fingerprint},
            "relationships": {"license": {"data": {"type": "licenses", "id": license_id}}}
        }
    }
    auth_headers = {"Authorization": f"Bearer {PRODUCT_TOKEN}", **headers}
    try:
        r = requests.post(f"{API_BASE_URL}/machines", json=activation_payload, headers=auth_headers)
        r.raise_for_status()
        # Retorna os dados da validação original para serem salvos, como no script antigo
        return validation_data, "Ativação bem-sucedida."
    except requests.exceptions.RequestException as e:
        if e.response and e.response.status_code == 422:
            error_detail = e.response.json().get('errors', [{}])[0]
            if error_detail.get('code') == 'FINGERPRINT_ALREADY_TAKEN':
                return validation_data, "Máquina já estava ativada."
        return None, "Não foi possível ativar esta máquina. A licença pode estar em uso ou sem vagas."


def save_license_data(license_data):
    try:
        with open(LICENSE_FILE_PATH, "w", encoding='utf-8') as f:
            json.dump(license_data, f, indent=2)
    except Exception:
        messagebox.showerror("Erro ao Guardar", f"Não foi possível guardar o ficheiro de licença em:\n{LICENSE_FILE_PATH}")

def load_license_data():
    if os.path.exists(LICENSE_FILE_PATH):
        try:
            with open(LICENSE_FILE_PATH, "r", encoding='utf-8') as f:
                return json.load(f)
        except Exception: return None
    return None

def check_license(parent_window):
    """
    Função principal corrigida.
    1. Tenta carregar a licença do cache.
    2. Se encontrar, REVALIDA online para garantir que ainda é válida.
    3. Se não houver cache ou a revalidação falhar, pede uma nova ativação.
    """
    fingerprint = get_machine_fingerprint()
    stored_data = load_license_data()

    if stored_data:
        license_id = stored_data.get("data", {}).get("id")
        if license_id:
            # CORREÇÃO: Sempre revalida a licença do cache online
            validation_result = validate_license_with_id(license_id, fingerprint)
            if validation_result and validation_result.get("meta", {}).get("valid"):
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
        
        parent_window.config(cursor="watch")
        future = _EXECUTOR.submit(activate_new_license, license_key_input, fingerprint)
        
        while not future.done():
            parent_window.update()
        
        parent_window.config(cursor="")
        activation_data, message = future.result()

        if activation_data:
            # O formato salvo é o mesmo do script antigo, garantindo consistência
            save_license_data(activation_data)
            
            # <<< --- CORREÇÃO 2 --- >>>
            # Atualiza o estado global para VÁLIDO após nova ativação
            set_license_as_valid()
            # <<< ------------------ >>>

            messagebox.showinfo("Sucesso", message, parent=parent_window)
            return True, activation_data
        else:
            if not messagebox.askretrycancel("Falha na Ativação", f"{message}\nDeseja tentar novamente?", parent=parent_window):
                return False, None