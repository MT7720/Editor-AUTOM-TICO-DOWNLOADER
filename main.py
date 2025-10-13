"""Ponto de entrada principal do aplicativo."""

from __future__ import annotations
import sys
import os
import traceback
import platform
from datetime import datetime
import ttkbootstrap as ttk
from tkinter import messagebox

# --- MÓDULOS DE SEGURANÇA E LICENCIAMENTO ---
import license_checker
from security.runtime_guard import enforce_runtime_safety, schedule_integrity_check, SecurityViolation
# ---------------------------------------------

import gui
import gui.config_manager as gui_config_manager
from gui import (
    VideoEditorApp,
    SUBTITLE_POSITIONS,
    CONFIG_FILE as _CONFIG_FILE,
    ConfigManager as _ConfigManager,
    APP_NAME,
)
from gui import constants as gui_constants

__all__ = ["ConfigManager", "VideoEditorApp", "SUBTITLE_POSITIONS", "CONFIG_FILE", "print_usage"]

CONFIG_FILE = _CONFIG_FILE

def _sync_config_file_path() -> None:
    gui.CONFIG_FILE = CONFIG_FILE
    gui_constants.CONFIG_FILE = CONFIG_FILE
    gui_config_manager.CONFIG_FILE = CONFIG_FILE

def setup_crash_log():
    log_dir = os.path.dirname(os.path.abspath(sys.argv[0])) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    log_file_path = os.path.join(log_dir, "crash_log.txt")
    try:
        if os.path.exists(log_file_path) and os.path.getsize(log_file_path) > 1 * 1024 * 1024:
            with open(log_file_path, 'w') as f: f.write(f"--- Log resetado em {datetime.now()} ---\n\n")
        log_file = open(log_file_path, 'a', encoding='utf-8', buffering=1)
        sys.stdout = log_file
        sys.stderr = log_file
    except Exception as e:
        print(f"Não foi possível criar o arquivo de log: {e}")

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        print("--- EXCEÇÃO NÃO TRATADA ---", file=sys.stderr)
        print(f"Data/Hora: {datetime.now()}", file=sys.stderr)
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)
        print("--------------------------\n", file=sys.stderr)

    sys.excepthook = handle_exception

class ConfigManager:
    @staticmethod
    def load_config() -> dict:
        _sync_config_file_path()
        return _ConfigManager.load_config()
    @staticmethod
    def save_config(config: dict) -> None:
        _sync_config_file_path()
        _ConfigManager.save_config(config)

def print_usage() -> None:
    print("Uso: python main.py")

if __name__ == "__main__":
    if getattr(sys, 'frozen', False):
        effects_dir = os.path.join(os.path.dirname(sys.executable), "effects")
        os.makedirs(effects_dir, exist_ok=True)
        setup_crash_log()
    
    print(f"--- Iniciando {APP_NAME} em {datetime.now()} ---")
    print(f"Sistema: {platform.system()} {platform.release()}")

    # 1. VERIFICAÇÃO DE SEGURANÇA INICIAL
    try:
        enforce_runtime_safety()
    except SecurityViolation as exc:
        messagebox.showerror(APP_NAME, f"Violação de segurança detectada:\n{exc}\nO programa será encerrado.")
        sys.exit(2)
    
    # Cria a janela principal mas a mantém escondida por enquanto
    root = ttk.Window(themename="superhero")
    root.withdraw()

    try:
        # 2. VERIFICAÇÃO DA LICENÇA
        print("Verificando licença...")
        
        # --- LÓGICA CORRIGIDA ---
        # A janela principal (root) é passada para o verificador de licença.
        # Ele a usará como "mãe" para a janela de ativação, se necessário.
        is_licensed, license_data = license_checker.check_license(root)

        if is_licensed:
            print("Licença validada. Iniciando a interface principal...")
            
            # 3. AGENDAMENTO DAS VERIFICAÇÕES DE SEGURANÇA CONTÍNUAS
            schedule_integrity_check()
            
            # Agora que a licença está validada, construímos e mostramos a aplicação principal
            app = VideoEditorApp(root=root, license_data=license_data)
            root.deiconify() # Mostra a janela principal
            root.mainloop()
            print("A interface principal foi encerrada normalmente.")
        else:
            print("Licença inválida ou não fornecida. Encerrando.")
            root.destroy()
            sys.exit(1)
            
    except Exception:
        print("Ocorreu um erro fatal durante a inicialização do programa.", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        messagebox.showerror("Erro Fatal", "Ocorreu um erro inesperado e o programa precisa ser fechado. Verifique o crash_log.txt para detalhes.")
        sys.exit(1)