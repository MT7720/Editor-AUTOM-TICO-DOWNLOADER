"""Gera o arquivo ``security/runtime_manifest.json`` com os recursos protegidos."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable

# Arquivo que será gerado
MANIFEST_PATH = Path("security/runtime_manifest.json")
ALGORITHM = "sha256"

# Recursos críticos que devem ser validados em tempo de execução. Os caminhos são
# relativos à raiz do pacote empacotado pelo PyInstaller (``_MEIPASS``).
RESOURCES_TO_PROTECT: Dict[str, Dict[str, object]] = {
    "ffmpeg_binary": {
        "path": "ffmpeg/ffmpeg-7.1.1-essentials_build/bin/ffmpeg.exe",
        "normalize_newlines": False,
        "description": "Binário principal utilizado para processamento de mídia.",
    },
    "license_authority_public_key": {
        "path": "security/license_authority_public_key.json",
        "normalize_newlines": True,
        "description": "Material público utilizado para validar licenças emitidas.",
    },
    "processing_pipeline": {
        "path": "processing/ffmpeg_pipeline.py",
        "normalize_newlines": True,
        "description": "Pipeline que orquestra as chamadas ao FFmpeg.",
    },
    "process_manager": {
        "path": "processing/process_manager.py",
        "normalize_newlines": True,
        "description": "Coordenador de subprocessos e validações de execução.",
    },
}


def _build_resource_payload() -> Dict[str, Dict[str, object]]:
    def _allowed_keys(data: Dict[str, object]) -> Dict[str, object]:
        allowed: Iterable[str] = ("path", "normalize_newlines")
        return {key: data[key] for key in allowed}

    return {name: _allowed_keys(data) for name, data in RESOURCES_TO_PROTECT.items()}


def main() -> None:
    """Regenera o manifesto com a lista de recursos críticos."""

    print("Gerando runtime_manifest.json com a lista de recursos críticos...")

    manifest_data = {
        "algorithm": ALGORITHM,
        "executables": {},
        "resources": _build_resource_payload(),
    }

    # Garante que a pasta 'security' exista
    MANIFEST_PATH.parent.mkdir(exist_ok=True)
    serialized_manifest = json.dumps(manifest_data, indent=4, sort_keys=True)
    MANIFEST_PATH.write_text(f"{serialized_manifest}\n", encoding="utf-8")

    print("-" * 30)
    print(f"Manifesto salvo em '{MANIFEST_PATH}'.")
    print(
        "Execute 'python tools/sign_runtime_manifest.py --base-dir .' para preencher hashes "
        "e assinaturas com a chave HMAC protegida."
    )


if __name__ == "__main__":
    main()
