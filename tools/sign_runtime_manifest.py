#!/usr/bin/env python3
"""Assina o manifesto de segurança utilizando uma chave HMAC externa.

Este script é destinado ao pipeline de build e não deve ser executado em
ambientes onde a chave não esteja protegida. A chave pode ser fornecida via
variável de ambiente ``RUNTIME_GUARD_HMAC_KEY`` (codificada em Base64) ou por
arquivo.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
from pathlib import Path
from typing import Dict, Tuple

import hashlib
import hmac

ENV_VAR_NAME = "RUNTIME_GUARD_HMAC_KEY"


def _decode_key(raw_key: str) -> bytes:
    try:
        key = base64.b64decode(raw_key, validate=True)
    except (binascii.Error, ValueError) as exc:  # pragma: no cover - validação defensiva
        raise SystemExit(f"Falha ao decodificar chave HMAC: {exc}") from exc
    if not key:
        raise SystemExit("Chave HMAC decodificada é vazia; verifique o segredo informado")
    return key


def load_key(args: argparse.Namespace) -> bytes:
    if args.key_file:
        raw = Path(args.key_file).read_text(encoding="utf-8").strip()
        return _decode_key(raw)

    raw = os.environ.get(ENV_VAR_NAME)
    if not raw:
        raise SystemExit(
            "Chave HMAC não fornecida. Defina RUNTIME_GUARD_HMAC_KEY ou use --key-file."
        )
    return _decode_key(raw)


def compute_hash(path: Path, algorithm: str, normalize_newlines: bool) -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            if normalize_newlines:
                chunk = chunk.replace(b"\r\n", b"\n")
            h.update(chunk)
    return h.hexdigest()


def sign_hash(key: bytes, digest: str) -> str:
    return hmac.new(key, digest.encode("utf-8"), hashlib.sha256).hexdigest()


def parse_executable_args(values: Tuple[str, ...]) -> Dict[str, Path]:
    mapping: Dict[str, Path] = {}
    for item in values:
        if "=" not in item:
            raise SystemExit("Parâmetros de executável devem seguir o formato nome=caminho")
        name, path = item.split("=", 1)
        mapping[name.strip()] = Path(path).expanduser().resolve()
    return mapping


def sign_manifest(args: argparse.Namespace) -> None:
    key = load_key(args)
    manifest_path = Path(args.manifest).resolve()
    base_dir = Path(args.base_dir).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    algorithm = manifest.get("algorithm", "sha256")
    resources = manifest.get("resources", {})
    executables = manifest.get("executables", {})

    executable_paths = parse_executable_args(tuple(args.executable or ()))

    for name, resource in resources.items():
        rel_path = resource.get("path")
        if not rel_path:
            raise SystemExit(f"Recurso '{name}' não possui caminho definido no manifesto")
        file_path = (base_dir / rel_path).resolve()
        if not file_path.exists():
            raise SystemExit(f"Arquivo de recurso não encontrado: {file_path}")
        normalize = bool(resource.get("normalize_newlines"))
        digest = compute_hash(file_path, algorithm, normalize)
        resource["hash"] = digest
        resource["signature"] = sign_hash(key, digest)

    for name, entry in executables.items():
        executable_path = executable_paths.get(name)
        if executable_path:
            if not executable_path.exists():
                raise SystemExit(f"Executável '{name}' não encontrado em {executable_path}")
            digest = compute_hash(executable_path, algorithm, False)
            entry["hash"] = digest
        elif not entry.get("hash"):
            raise SystemExit(
                f"Nenhum hash informado para o executável '{name}'. Forneça --executable {name}=caminho."
            )
        entry_hash = entry.get("hash")
        if not entry_hash:
            raise SystemExit(f"Hash ausente para o executável '{name}'")
        entry["signature"] = sign_hash(key, entry_hash)

    manifest_path.write_text(json.dumps(manifest, indent=4, sort_keys=True), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assina o manifesto do runtime guard")
    parser.add_argument(
        "--manifest",
        default="security/runtime_manifest.json",
        help="Caminho para o manifesto a ser assinado (JSON)",
    )
    parser.add_argument(
        "--base-dir",
        default=".",
        help="Diretório base para resolução dos caminhos dos recursos",
    )
    parser.add_argument(
        "--executable",
        action="append",
        metavar="NOME=CAMINHO",
        help="Mapeia uma entrada de executável para o caminho gerado durante o build",
    )
    parser.add_argument(
        "--key-file",
        help="Arquivo contendo a chave HMAC codificada em Base64 (alternativa à variável de ambiente)",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    sign_manifest(args)


if __name__ == "__main__":  # pragma: no cover - execução via CLI
    main()
