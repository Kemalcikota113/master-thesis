"""
Utilities for scaffolding Vue 3 + TypeScript + Vite projects.
"""

import json
import subprocess
from pathlib import Path
from typing import List


def scaffold_vue_project(output_dir: Path, project_name: str):
    """
    Creates a complete Vue 3 + TypeScript + Vite project structure.

    Generates:
    - package.json with all dependencies
    - tsconfig.json for TypeScript configuration
    - vite.config.ts for Vite bundler
    - index.html entry point
    - src/main.ts application entry
    - src/env.d.ts for Vue type declarations
    - src/components/ directory for translated components

    Args:
        output_dir: Path where the project should be created
        project_name: Name of the project (for package.json)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create package.json
    package_json = {
        "name": project_name,
        "version": "0.1.0",
        "private": True,
        "type": "module",
        "scripts": {
            "dev": "vite",
            "build": "vue-tsc && vite build",
            "preview": "vite preview",
            "type-check": "vue-tsc --noEmit"
        },
        "dependencies": {
            "vue": "^3.4.0"
        },
        "devDependencies": {
            "@vitejs/plugin-vue": "^5.0.0",
            "typescript": "^5.3.0",
            "vite": "^5.0.0",
            "vue-tsc": "^1.8.27",
            "eslint": "^8.56.0",
            "eslint-plugin-vue": "^9.20.0",
            "@typescript-eslint/parser": "^6.19.0",
            "@typescript-eslint/eslint-plugin": "^6.19.0"
        }
    }

    with open(output_dir / "package.json", 'w') as f:
        json.dump(package_json, f, indent=2)

    # Create tsconfig.json
    tsconfig = {
        "compilerOptions": {
            "target": "ES2020",
            "useDefineForClassFields": True,
            "module": "ESNext",
            "lib": ["ES2020", "DOM", "DOM.Iterable"],
            "skipLibCheck": True,
            "moduleResolution": "bundler",
            "allowImportingTsExtensions": True,
            "resolveJsonModule": True,
            "isolatedModules": True,
            "noEmit": True,
            "jsx": "preserve",
            "strict": True,
            "noUnusedLocals": True,
            "noUnusedParameters": True,
            "noFallthroughCasesInSwitch": True,
            "baseUrl": ".",
            "paths": {
                "@/*": ["./src/*"]
            }
        },
        "include": ["src/**/*.ts", "src/**/*.tsx", "src/**/*.vue"],
        "references": [{"path": "./tsconfig.node.json"}]
    }

    with open(output_dir / "tsconfig.json", 'w') as f:
        json.dump(tsconfig, f, indent=2)

    # Create tsconfig.node.json (for Vite config)
    tsconfig_node = {
        "compilerOptions": {
            "composite": True,
            "skipLibCheck": True,
            "module": "ESNext",
            "moduleResolution": "bundler",
            "allowSyntheticDefaultImports": True
        },
        "include": ["vite.config.ts"]
    }

    with open(output_dir / "tsconfig.node.json", 'w') as f:
        json.dump(tsconfig_node, f, indent=2)

    # Create vite.config.ts
    vite_config = '''import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  }
})
'''

    with open(output_dir / "vite.config.ts", 'w') as f:
        f.write(vite_config)

    # Create index.html
    index_html = '''<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Vue Translation Output</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
'''

    with open(output_dir / "index.html", 'w') as f:
        f.write(index_html)

    # Create src directory structure
    src_dir = output_dir / "src"
    src_dir.mkdir(exist_ok=True)
    (src_dir / "components").mkdir(exist_ok=True)

    # Create src/env.d.ts (Vue type declarations)
    env_d_ts = '''/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}
'''

    with open(src_dir / "env.d.ts", 'w') as f:
        f.write(env_d_ts)

    # Create placeholder src/main.ts (will be updated by generate_app_vue)
    main_ts = '''import { createApp } from 'vue'
import App from './App.vue'

createApp(App).mount('#app')
'''

    with open(src_dir / "main.ts", 'w') as f:
        f.write(main_ts)

    # Create .eslintrc.cjs
    eslintrc = '''{
  root: true,
  env: {
    node: true,
  },
  extends: [
    'eslint:recommended',
    'plugin:vue/vue3-recommended',
    '@vue/typescript/recommended',
  ],
  parserOptions: {
    ecmaVersion: 2020,
  },
  rules: {
    'vue/multi-word-component-names': 'off',
  },
}
'''

    with open(output_dir / ".eslintrc.cjs", 'w') as f:
        f.write(eslintrc)

    print(f"✅ Scaffolded Vue 3 project at: {output_dir}")


def generate_app_vue(output_dir: Path, component_list: List[str]):
    """
    Generates App.vue that imports and displays all translated components.

    Args:
        output_dir: Path to the Vue project root
        component_list: List of component names (without .vue extension)
    """
    src_dir = output_dir / "src"

    if not component_list:
        # Create a minimal App.vue
        app_vue = '''<template>
  <div id="app">
    <h1>No components to display</h1>
    <p>Translation completed but no components were generated.</p>
  </div>
</template>

<script setup lang="ts">
// Empty application
</script>

<style>
#app {
  font-family: Avenir, Helvetica, Arial, sans-serif;
  text-align: center;
  color: #2c3e50;
  margin-top: 60px;
}
</style>
'''
        with open(src_dir / "App.vue", 'w') as f:
            f.write(app_vue)
        return

    # Generate imports
    imports = []
    for component_name in component_list:
        # Handle nested paths: "components/pages/Home" -> "./components/pages/Home.vue"
        component_path = f"./{component_name}.vue"
        imports.append(f"import {Path(component_name).stem} from '{component_path}'")

    imports_str = '\n'.join(imports)

    # Generate component list for template
    component_names = [Path(name).stem for name in component_list]

    # Create App.vue
    app_vue = f'''<template>
  <div id="app">
    <h1>Translated Components</h1>
    <div class="components-container">
      <!-- Display all translated components -->
      {chr(10).join(f"      <{name} />" for name in component_names[:5])}
      {f"      <!-- {len(component_names) - 5} more components -->" if len(component_names) > 5 else ""}
    </div>
  </div>
</template>

<script setup lang="ts">
{imports_str}
</script>

<style>
#app {{
  font-family: Avenir, Helvetica, Arial, sans-serif;
  text-align: center;
  color: #2c3e50;
  margin-top: 60px;
}}

.components-container {{
  margin-top: 20px;
}}
</style>
'''

    with open(src_dir / "App.vue", 'w') as f:
        f.write(app_vue)

    print(f"✅ Generated App.vue with {len(component_list)} component imports")


def run_npm_install(project_dir: Path) -> bool:
    """
    Runs npm install in the project directory.

    Args:
        project_dir: Path to the Vue project root

    Returns:
        True if successful, False otherwise
    """
    print(f"\n📦 Running npm install in {project_dir}...")

    try:
        result = subprocess.run(
            ["npm", "install"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode == 0:
            print("✅ npm install completed successfully")
            return True
        else:
            print(f"❌ npm install failed:")
            print(result.stderr)
            return False

    except subprocess.TimeoutExpired:
        print("❌ npm install timed out after 5 minutes")
        return False
    except FileNotFoundError:
        print("❌ npm not found. Please install Node.js and npm.")
        return False


def preserve_directory_structure(
    relative_path: str,
    output_dir: Path
) -> Path:
    """
    Creates nested directory structure and returns the output file path.

    Converts filenames to PascalCase to match Vue component naming conventions
    (e.g., view.js → View.vue, app.js → App.vue).

    Args:
        relative_path: Relative path from dataset root (e.g., "src/components/Home.js")
        output_dir: Vue project root directory

    Returns:
        Path where the .vue file should be written

    Example:
        >>> preserve_directory_structure("src/view.js", Path("output/vue"))
        Path("output/vue/src/View.vue")
    """
    # Convert .js to .vue
    vue_path = Path(relative_path).with_suffix('.vue')

    # Strip leading "src/" if present to avoid double src/ prefix
    # Files from datasets/project/src/app.js should go to output/project/src/app.vue
    # NOT output/project/src/src/app.vue
    vue_path_str = str(vue_path)
    if vue_path_str.startswith('src/') or vue_path_str.startswith('src\\'):
        vue_path_str = vue_path_str[4:]  # Remove "src/" or "src\" prefix

    # Convert filename to PascalCase (Vue component naming convention)
    # e.g., view.vue → View.vue, app.vue → App.vue, todo-item.vue → TodoItem.vue
    path_parts = Path(vue_path_str).parts
    if path_parts:
        # Get filename without extension
        filename = Path(path_parts[-1]).stem
        extension = Path(path_parts[-1]).suffix

        # Convert to PascalCase
        # Handle kebab-case and snake_case: todo-item → TodoItem, todo_item → TodoItem
        pascal_name = ''.join(word.capitalize() for word in filename.replace('-', '_').split('_'))
        pascal_filename = pascal_name + extension

        # Reconstruct path with PascalCase filename
        if len(path_parts) > 1:
            vue_path = Path(*path_parts[:-1]) / pascal_filename
        else:
            vue_path = Path(pascal_filename)
    else:
        vue_path = Path(vue_path_str)

    # Create full output path
    output_path = output_dir / "src" / vue_path

    # Create parent directories
    output_path.parent.mkdir(parents=True, exist_ok=True)

    return output_path


def copy_static_assets(
    css_files: list,
    output_dir: Path
):
    """
    Copies CSS files to the Vue project.

    Args:
        css_files: List of (relative_path, absolute_path) tuples for CSS files
        output_dir: Vue project root directory
    """
    import shutil

    for relative_path, absolute_path in css_files:
        # Strip "src/" prefix if present
        rel_path_str = str(relative_path)
        if rel_path_str.startswith('src/') or rel_path_str.startswith('src\\'):
            rel_path_str = rel_path_str[4:]

        # Copy to output/src/assets/ directory
        output_path = output_dir / "src" / "assets" / rel_path_str

        # Create parent directories
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy file
        shutil.copy2(absolute_path, output_path)
        print(f"   Copied CSS: {relative_path} → {output_path.relative_to(output_dir)}")
