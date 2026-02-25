"""File discovery utilities for C datasets."""

from pathlib import Path


EXCLUDED_DIRS = {
    ".git",
    "build",
    "dist",
    "target",
    "node_modules",
    "__pycache__",
    "tests",
    "test",
    "fuzzing",
    "examples",
}


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.parts)


def discover_c_files(dataset_path: str | Path) -> list[tuple[str, Path]]:
    """Discover .c files, excluding test/fuzz folders by default."""
    root = Path(dataset_path)
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Dataset directory not found: {root}")

    files: list[tuple[str, Path]] = []
    for path in root.rglob("*.c"):
        if _is_excluded(path.relative_to(root)):
            continue
        files.append((str(path.relative_to(root)), path))

    files.sort(key=lambda item: item[0])
    return files


def discover_header_files(dataset_path: str | Path) -> list[tuple[str, Path]]:
    """Discover .h files used as translation context only."""
    root = Path(dataset_path)
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Dataset directory not found: {root}")

    files: list[tuple[str, Path]] = []
    for path in root.rglob("*.h"):
        if _is_excluded(path.relative_to(root)):
            continue
        files.append((str(path.relative_to(root)), path))

    files.sort(key=lambda item: item[0])
    return files


def build_header_context(
    header_files: list[tuple[str, Path]],
    max_chars: int = 20000,
) -> str:
    """Build bounded header context string for prompts."""
    if not header_files:
        return "(no header files found)"

    blocks: list[str] = []
    total = 0
    for rel_path, abs_path in header_files:
        try:
            content = abs_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        block = f"// FILE: {rel_path}\n{content.strip()}\n"
        if total + len(block) > max_chars:
            remaining = max_chars - total
            if remaining > 200:
                blocks.append(block[:remaining])
            break

        blocks.append(block)
        total += len(block)

    if not blocks:
        return "(header files unreadable)"
    return "\n".join(blocks)
