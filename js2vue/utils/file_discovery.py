"""
Utilities for discovering JavaScript source files in datasets.
"""

from pathlib import Path
from typing import List, Tuple


# Directories to exclude from file discovery
EXCLUDED_DIRS = {
    'node_modules',
    'dist',
    'build',
    'test',
    'tests',
    '__tests__',
    'e2e',
    '.git',
    '.vscode',
    '.idea',
    'coverage'
}

# File patterns to exclude
EXCLUDED_PATTERNS = {
    'webpack.config.js',
    'webpack.*.js',
    'jest.config.js',
    'jest.*.js',
    'vite.config.js',
    'vite.*.js',
    'rollup.config.js',
    'babel.config.js',
    '.eslintrc.js',
    'postcss.config.js'
}


def should_exclude_file(file_path: Path) -> bool:
    """
    Determines if a file should be excluded from discovery.

    Args:
        file_path: Path to the file

    Returns:
        True if the file should be excluded, False otherwise
    """
    filename = file_path.name

    # Check exact matches
    if filename in EXCLUDED_PATTERNS:
        return True

    # Check wildcard patterns
    for pattern in EXCLUDED_PATTERNS:
        if '*' in pattern:
            prefix, suffix = pattern.split('*', 1)
            if filename.startswith(prefix) and filename.endswith(suffix):
                return True

    return False


def should_exclude_directory(dir_path: Path) -> bool:
    """
    Determines if a directory should be excluded from traversal.

    Args:
        dir_path: Path to the directory

    Returns:
        True if the directory should be excluded, False otherwise
    """
    return dir_path.name in EXCLUDED_DIRS


def discover_js_files(dataset_path: str | Path) -> List[Tuple[str, Path]]:
    """
    Recursively discovers JavaScript files in a dataset directory.

    Preserves directory structure for output mapping. Excludes:
    - Build/dependency directories (node_modules, dist, test, etc.)
    - Build configuration files (webpack, jest, etc.)

    Args:
        dataset_path: Path to the dataset root directory

    Returns:
        List of tuples: (relative_path, absolute_path)
        - relative_path: Path relative to dataset root (for structure preservation)
        - absolute_path: Full filesystem path

    Example:
        >>> discover_js_files("datasets/realworld-js")
        [
            ("src/components/Home.js", Path(".../datasets/realworld-js/src/components/Home.js")),
            ("src/utils/api.js", Path(".../datasets/realworld-js/src/utils/api.js"))
        ]
    """
    dataset_path = Path(dataset_path)

    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset path does not exist: {dataset_path}")

    if not dataset_path.is_dir():
        raise NotADirectoryError(f"Dataset path is not a directory: {dataset_path}")

    # Determine search root: prefer src/ if it exists, otherwise use root
    search_root = dataset_path / "src" if (dataset_path / "src").exists() else dataset_path

    discovered_files = []

    def traverse(current_path: Path, relative_base: Path):
        """Recursive traversal helper."""
        if not current_path.is_dir():
            return

        if should_exclude_directory(current_path):
            return

        for item in current_path.iterdir():
            if item.is_dir():
                traverse(item, relative_base)
            elif item.is_file() and item.suffix == '.js':
                if not should_exclude_file(item):
                    relative_path = str(item.relative_to(relative_base))
                    discovered_files.append((relative_path, item))

    # Start traversal
    traverse(search_root, dataset_path)

    # Sort by relative path for consistent ordering
    discovered_files.sort(key=lambda x: x[0])

    return discovered_files


def discover_static_assets(dataset_path: str | Path) -> dict:
    """
    Discovers HTML and CSS files in a dataset directory.

    Args:
        dataset_path: Path to the dataset root directory

    Returns:
        Dictionary with 'html' and 'css' keys containing lists of (relative_path, absolute_path) tuples

    Example:
        >>> discover_static_assets("datasets/todomvc-es6")
        {
            'html': [("src/index.html", Path(".../datasets/todomvc-es6/src/index.html"))],
            'css': [("src/app.css", Path(".../datasets/todomvc-es6/src/app.css"))]
        }
    """
    dataset_path = Path(dataset_path)

    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset path does not exist: {dataset_path}")

    # Search in src/ if it exists, otherwise root
    search_root = dataset_path / "src" if (dataset_path / "src").exists() else dataset_path

    html_files = []
    css_files = []

    def traverse(current_path: Path, relative_base: Path):
        """Recursive traversal helper."""
        if not current_path.is_dir():
            return

        if should_exclude_directory(current_path):
            return

        for item in current_path.iterdir():
            if item.is_dir():
                traverse(item, relative_base)
            elif item.is_file():
                relative_path = str(item.relative_to(relative_base))
                if item.suffix == '.html':
                    html_files.append((relative_path, item))
                elif item.suffix == '.css':
                    css_files.append((relative_path, item))

    # Start traversal
    traverse(search_root, dataset_path)

    return {
        'html': sorted(html_files, key=lambda x: x[0]),
        'css': sorted(css_files, key=lambda x: x[0])
    }


def get_component_name(file_path: str | Path) -> str:
    """
    Extracts a component name from a file path.

    Args:
        file_path: Path to the JavaScript file

    Returns:
        Component name (PascalCase, suitable for Vue component)

    Examples:
        >>> get_component_name("src/components/Home.js")
        "Home"
        >>> get_component_name("utils/api-client.js")
        "ApiClient"
    """
    file_path = Path(file_path)
    stem = file_path.stem  # Filename without extension

    # Convert kebab-case or snake_case to PascalCase
    parts = stem.replace('-', '_').split('_')
    return ''.join(word.capitalize() for word in parts)
