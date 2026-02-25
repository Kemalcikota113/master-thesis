"""Utilities for creating and populating a minimal Rust project."""

import re
from pathlib import Path


def _sanitize_package_name(name: str) -> str:
    lowered = name.lower().replace("_", "-")
    cleaned = re.sub(r"[^a-z0-9-]", "-", lowered)
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "translated-project"


def _sanitize_lib_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        cleaned = "translated_project"
    if cleaned[0].isdigit():
        cleaned = f"m_{cleaned}"
    return cleaned.lower()


def relative_c_to_module_name(relative_c_path: str) -> str:
    """Map a C file path to a flat Rust module name."""
    stem = relative_c_path.replace("\\", "/")
    stem = stem[:-2] if stem.endswith(".c") else stem
    stem = stem.replace("/", "_").replace("-", "_").replace(".", "_")
    stem = re.sub(r"[^a-zA-Z0-9_]", "_", stem)
    stem = re.sub(r"_+", "_", stem).strip("_")
    if not stem:
        stem = "translated"
    if stem[0].isdigit():
        stem = f"m_{stem}"
    return stem.lower()


def scaffold_rust_project(output_dir: Path, project_name: str):
    """Create minimal Rust crate structure for translated output."""
    output_dir.mkdir(parents=True, exist_ok=True)
    src_dir = output_dir / "src"
    translated_dir = src_dir / "translated"
    translated_dir.mkdir(parents=True, exist_ok=True)

    package_name = _sanitize_package_name(project_name)
    lib_name = _sanitize_lib_name(project_name)

    cargo_toml = f"""[package]
name = \"{package_name}\"
version = \"0.1.0\"
edition = \"2021\"

[lib]
name = \"{lib_name}\"
path = \"src/lib.rs\"

[dependencies]
"""
    (output_dir / "Cargo.toml").write_text(cargo_toml, encoding="utf-8")

    (src_dir / "lib.rs").write_text("pub mod translated;\n", encoding="utf-8")
    (translated_dir / "mod.rs").write_text("", encoding="utf-8")


def write_translated_file(output_dir: Path, module_name: str, rust_code: str) -> Path:
    """Write one translated Rust module file and return its path."""
    translated_dir = output_dir / "src" / "translated"
    translated_dir.mkdir(parents=True, exist_ok=True)
    file_path = translated_dir / f"{module_name}.rs"
    file_path.write_text(rust_code + "\n", encoding="utf-8")
    return file_path


def write_module_index(output_dir: Path, module_names: list[str]):
    """Write src/translated/mod.rs with discovered module declarations."""
    translated_dir = output_dir / "src" / "translated"
    lines = [f"pub mod {name};" for name in sorted(set(module_names))]
    content = "\n".join(lines)
    if content:
        content += "\n"
    (translated_dir / "mod.rs").write_text(content, encoding="utf-8")
