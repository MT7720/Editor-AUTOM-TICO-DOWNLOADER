import hashlib

from security import runtime_guard


def test_calculate_file_hash_normalizes_crlf_across_chunks(tmp_path):
    chunk_size = 65536
    data = b"A" * (chunk_size - 1) + b"\r" + b"\nB\r\nC"
    file_path = tmp_path / "text.txt"
    file_path.write_bytes(data)

    normalized = data.replace(b"\r\n", b"\n")
    expected_normalized_hash = hashlib.sha256(normalized).hexdigest()
    expected_raw_hash = hashlib.sha256(data).hexdigest()

    assert (
        runtime_guard._calculate_file_hash(file_path, "sha256", True)
        == expected_normalized_hash
    )
    assert (
        runtime_guard._calculate_file_hash(file_path, "sha256", False)
        == expected_raw_hash
    )


def test_collect_resource_violations_respects_normalize_flag(monkeypatch, tmp_path):
    base_dir = tmp_path / "bundle"
    base_dir.mkdir()

    text_path = base_dir / "text.txt"
    text_path.write_bytes(b"line1\r\nline2\r\n")

    binary_path = base_dir / "binary.bin"
    binary_content = b"\x00\xff\r\n\xaa\xbb"
    binary_path.write_bytes(binary_content)

    algorithm = "sha256"

    text_hash = runtime_guard._calculate_file_hash(text_path, algorithm, True)
    binary_hash = runtime_guard._calculate_file_hash(binary_path, algorithm, False)

    manifest = {
        "algorithm": algorithm,
        "resources": {
            "text": {
                "path": "text.txt",
                "hash": text_hash,
                "signature": "sig-text",
                "normalize_newlines": True,
            },
            "binary": {
                "path": "binary.bin",
                "hash": binary_hash,
                "signature": "sig-binary",
                "normalize_newlines": False,
            },
        },
    }

    monkeypatch.setattr(runtime_guard, "_verify_signature", lambda *_: True)
    monkeypatch.setattr(runtime_guard, "_get_internal_base_path", lambda: base_dir)

    assert runtime_guard._collect_resource_violations(manifest) == []


def test_collect_resource_violations_default_to_raw_bytes(monkeypatch, tmp_path):
    base_dir = tmp_path / "bundle"
    base_dir.mkdir()

    resource_path = base_dir / "resource.bin"
    resource_bytes = b"\x01\x02\r\n\x03"
    resource_path.write_bytes(resource_bytes)

    algorithm = "sha256"
    raw_hash = runtime_guard._calculate_file_hash(resource_path, algorithm, False)
    normalized_hash = runtime_guard._calculate_file_hash(resource_path, algorithm, True)

    manifest = {
        "algorithm": algorithm,
        "resources": {
            "resource": {
                "path": "resource.bin",
                "hash": raw_hash,
                "signature": "sig-resource",
            }
        },
    }

    monkeypatch.setattr(runtime_guard, "_verify_signature", lambda *_: True)
    monkeypatch.setattr(runtime_guard, "_get_internal_base_path", lambda: base_dir)

    assert runtime_guard._collect_resource_violations(manifest) == []

    manifest["resources"]["resource"]["hash"] = normalized_hash

    violations = runtime_guard._collect_resource_violations(manifest)
    assert violations
    assert "Hash divergente" in violations[0]
