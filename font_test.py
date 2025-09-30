import tkinter as tk
from tkinter import filedialog
from tkinter import font as tkFont
from pathlib import Path
import platform

# Tenta importar pyglet. Se não conseguir, o teste de fontes customizadas será desabilitado.
try:
    import pyglet
except ImportError:
    pyglet = None

class FontTestApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Teste Isolado de Fonte")
        self.root.geometry("600x400")

        # --- Componentes da Interface ---
        
        # Rótulo para exibir o texto de exemplo
        self.sample_label = tk.Label(
            root, 
            text="O rápido gambá marrom pula sobre o cão preguiçoso.", 
            font=("Arial", 20)
        )
        self.sample_label.pack(pady=50, padx=20)

        # Botão para selecionar o arquivo de fonte
        self.select_button = tk.Button(
            root, 
            text="Selecionar Fonte...", 
            font=("Arial", 12),
            command=self.load_font
        )
        self.select_button.pack(pady=10)

        # Rótulo para mostrar o status
        self.status_label = tk.Label(root, text="Nenhuma fonte carregada.", font=("Arial", 10))
        self.status_label.pack(pady=20)
        
        # Avisa se o pyglet não estiver instalado
        if not pyglet:
            self.status_label.config(text="AVISO: Pyglet não está instalado. O teste não funcionará.", fg="red")
            self.select_button.config(state="disabled")

    def load_font(self):
        """
        Abre a caixa de diálogo para selecionar um arquivo de fonte e tenta carregá-lo.
        """
        file_types = [("Arquivos de Fonte", "*.ttf *.otf"), ("Todos os arquivos", "*.*")]
        filepath = filedialog.askopenfilename(title="Selecione um arquivo de fonte", filetypes=file_types)

        if not filepath:
            return

        print("-" * 50)
        print(f"Arquivo selecionado: {filepath}")

        # --- Carregamento da Fonte com Pyglet ---
        try:
            pyglet.font.add_file(filepath)
            print("Pyglet -> pyglet.font.add_file() executado com sucesso.")
        except Exception as e:
            print(f"Pyglet -> ERRO ao carregar a fonte: {e}")
            self.status_label.config(text=f"Erro no Pyglet: {e}", fg="red")
            return
            
        # O nome da família da fonte é geralmente o nome do arquivo sem a extensão.
        # Esta é a parte mais crítica.
        font_name_from_file = Path(filepath).stem
        print(f"Tentando usar o nome de família da fonte: '{font_name_from_file}'")

        # --- Verificação e Aplicação no Tkinter ---
        
        # Lista todas as fontes que o Tkinter reconhece ANTES de tentar usar a nova.
        # Isso é útil para comparar.
        # families_before = sorted(tkFont.families())
        # print(f"\nTkinter -> {len(families_before)} famílias de fontes reconhecidas ANTES.")

        try:
            # Cria um objeto de fonte do Tkinter com o nome que extraímos.
            custom_font = tkFont.Font(family=font_name_from_file, size=24)
            
            # Aplica a fonte ao nosso rótulo de exemplo.
            self.sample_label.config(font=custom_font)
            
            # Verifica se a fonte aplicada é realmente a que queríamos.
            actual_font_info = custom_font.actual()
            actual_family = actual_font_info.get("family", "N/A")
            
            print(f"Tkinter -> Fonte aplicada com sucesso.")
            print(f"Tkinter -> Nome da família REALMENTE usada: '{actual_family}'")

            if actual_family.lower() == font_name_from_file.lower():
                self.status_label.config(text=f"Fonte '{actual_family}' aplicada com sucesso!", fg="green")
                print("\n✅ SUCESSO! O nome do arquivo corresponde à família da fonte.")
            else:
                self.status_label.config(
                    text=f"AVISO: A fonte foi aplicada, mas como '{actual_family}'.", 
                    fg="orange"
                )
                print(f"\n⚠️ AVISO: Tkinter aplicou a fonte, mas a reconheceu como '{actual_family}'.")
                print("Isso significa que no seu app principal, você deve usar este nome em vez do nome do arquivo.")

        except tk.TclError as e:
            # Este erro acontece se o Tkinter não encontrar a fonte de jeito nenhum.
            print(f"\n❌ ERRO: Tkinter não conseguiu encontrar ou usar a fonte '{font_name_from_file}'.")
            print(f"   Erro Tcl: {e}")
            self.status_label.config(text=f"Erro no Tkinter: Fonte '{font_name_from_file}' não encontrada.", fg="red")

if __name__ == "__main__":
    # Garante que a DPI seja tratada corretamente no Windows
    if platform.system() == "Windows":
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception as e:
            print(f"Não foi possível definir a conscientização de DPI: {e}")

    # Cria e executa a aplicação de teste
    root = tk.Tk()
    app = FontTestApp(root)
    root.mainloop()
