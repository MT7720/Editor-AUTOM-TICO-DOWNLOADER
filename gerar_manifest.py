import json
from pathlib import Path

# Arquivo que será gerado
MANIFEST_PATH = Path("security/runtime_manifest.json")
ALGORITHM = "sha256"

# A lista de arquivos a proteger está VAZIA.
# Isso é intencional para evitar erros de hash/assinatura em outras máquinas.
# A segurança principal virá das checagens anti-debugger e de licença.
ARQUIVOS_PARA_PROTEGER = []

def main():
    """Gera um manifesto de tempo de execução, intencionalmente simples para portabilidade."""
    print("Gerando novo runtime_manifest.json (configurado para máxima compatibilidade)...")

    manifest_data = {
        "algorithm": ALGORITHM,
        "executables": {},
        "resources": {} # Seção de recursos fica vazia
    }

    # Garante que a pasta 'security' exista
    MANIFEST_PATH.parent.mkdir(exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=4)

    print("-" * 30)
    print(f"Manifesto salvo com sucesso em '{MANIFEST_PATH}'")
    print("O manifesto foi gerado sem hashes de arquivos para garantir que o .exe funcione em qualquer PC.")

if __name__ == "__main__":
    main()