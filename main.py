"""Ponto de entrada principal do aplicativo.

Este módulo fornece uma camada fina que reexporta as classes e constantes
definidas em :mod:`video_editor_gui` para facilitar a importação em outros
locais (incluindo os testes unitários). Quando executado diretamente, abre a
interface gráfica.
"""

from __future__ import annotations
import sys
import os
import traceback
import platform
from datetime import datetime
import ttkbootstrap as ttk # Importa ttkbootstrap aqui
import license_checker
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

__all__ = [
    "ConfigManager",
    "VideoEditorApp",
    "SUBTITLE_POSITIONS",
    "CONFIG_FILE",
    "print_usage",
]

CONFIG_FILE = _CONFIG_FILE


def _sync_config_file_path() -> None:
    """Keep GUI modules aware of the overridden config path."""
    gui.CONFIG_FILE = CONFIG_FILE
    gui_constants.CONFIG_FILE = CONFIG_FILE
    gui_config_manager.CONFIG_FILE = CONFIG_FILE


def setup_crash_log():
    """Configura um arquivo de log para capturar erros fatais no .exe"""
    log_dir = os.path.dirname(os.path.abspath(sys.argv[0])) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    log_file_path = os.path.join(log_dir, "crash_log.txt")
    
    try:
        if os.path.exists(log_file_path) and os.path.getsize(log_file_path) > 1 * 1024 * 1024:
            with open(log_file_path, 'w') as f:
                f.write(f"--- Log resetado em {datetime.now()} ---\n\n")

        log_file = open(log_file_path, 'a', encoding='utf-8', buffering=1)
        sys.stdout = log_file
        sys.stderr = log_file
    except Exception as e:
        print(f"Não foi possível criar o arquivo de log: {e}")


    def handle_exception(exc_type, exc_value, exc_traceback):
        """Captura exceções não tratadas e as escreve no log."""
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
        global CONFIG_FILE
        _sync_config_file_path()
        return _ConfigManager.load_config()

    @staticmethod
    def save_config(config: dict) -> None:
        global CONFIG_FILE
        _sync_config_file_path()
        _ConfigManager.save_config(config)

def print_usage() -> None:
    print("Uso: python main.py [--help]")
    print("Sem argumentos, abre a interface gráfica do editor.")


if __name__ == "__main__":
    if getattr(sys, 'frozen', False):
        # Cria a pasta 'effects' se não existir, para os novos efeitos de vídeo
        effects_dir = os.path.join(os.path.dirname(sys.executable), "effects")
        os.makedirs(effects_dir, exist_ok=True)
        setup_crash_log()
    
    print(f"--- Iniciando {APP_NAME} em {datetime.now()} ---")
    print(f"Sistema Operacional: {platform.system()} {platform.release()}")
    print(f"Versão do Python: {sys.version}")

    if "--help" in sys.argv or "-h" in sys.argv:
        print_usage()
    else:
        # Cria a ÚNICA instância da janela principal do aplicativo.
        root = ttk.Window(themename="superhero")
        root.withdraw()  # Começa escondida.

        try:
            print("Verificando licença...")
            # Passa a janela principal para o verificador de licença usar.
            is_licensed, license_data = license_checker.check_license(root)

            if is_licensed:
                print("Licença validada. Iniciando a interface principal...")
                # A licença é válida, então construímos a aplicação na janela que já existe.
                app = VideoEditorApp(root=root, license_data=license_data)
                # Mostra a janela e inicia o programa.
                root.deiconify()
                root.mainloop()
                print("A interface principal foi encerrada normalmente.")
            else:
                print("Licença inválida ou não fornecida. Encerrando.")
                root.destroy() # Destrói a janela se a licença falhar.
                sys.exit(1)
        except Exception as e:
            print("Ocorreu um erro fatal durante a inicialização do programa.", file=sys.stderr)
            raise
