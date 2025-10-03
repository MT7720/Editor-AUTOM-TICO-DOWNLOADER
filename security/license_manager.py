"""Módulo para gerenciar o estado da licença e proteger funcionalidades."""

import sys
from functools import wraps
from tkinter import messagebox

# Estado global para armazenar o status da licença.
_LICENSE_VALID = False

class LicenseError(Exception):
    """Exceção levantada quando uma funcionalidade protegida é usada sem licença."""
    pass

def set_license_as_valid():
    """Marca a licença como válida para a sessão atual."""
    global _LICENSE_VALID
    _LICENSE_VALID = True

def is_license_valid() -> bool:
    """Verifica se a licença está marcada como válida."""
    return _LICENSE_VALID

def require_license(func):
    """
    Decorador que protege uma função, exigindo uma licença válida.
    Se a licença não for válida, impede a execução e encerra o programa.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not is_license_valid():
            # Mostra um alerta e encerra a aplicação de forma abrupta.
            # Isso é intencional para impedir o uso indevido.
            messagebox.showerror(
                "Licença Inválida",
                "Uma licença válida é necessária para executar esta ação. O programa será encerrado."
            )
            sys.exit("VIOLAÇÃO DE LICENÇA: Tentativa de acesso a funcionalidade protegida.")
        
        return func(*args, **kwargs)
    return wrapper
