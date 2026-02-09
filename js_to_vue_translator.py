#!/usr/bin/env python3
"""
JS to Vue 3 Translator
Converts a vanilla JavaScript project directory into a fully functional Vue 3 project.

Usage:
    python js_to_vue_translator.py <input_dir> <output_dir>
    
Example:
    python js_to_vue_translator.py ./input ./output
"""

import subprocess
import os
import re
import sys
import json
import shutil
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from .env file
load_dotenv()

# Configuration
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MAX_RETRIES = 3


def clean_llm_output(raw_output: str) -> str:
    """
    Strips markdown artifacts from LLM output to extract clean Vue SFC code.
    """
    code = raw_output.strip()
    
    # Pattern to match markdown code blocks with optional language identifier
    code_block_pattern = r'```(?:vue|html|typescript|ts|javascript|js)?\s*\n?(.*?)```'
    matches = re.findall(code_block_pattern, code, re.DOTALL | re.IGNORECASE)
    
    if matches:
        code = max(matches, key=len).strip()
    
    # Remove stray language identifiers at the beginning
    code = re.sub(r'^(vue|html|typescript|ts|javascript|js)\s*\n', '', code, flags=re.IGNORECASE)
    
    # Ensure it starts with a valid Vue SFC tag
    first_tag_match = re.search(r'(<template|<script|<style)', code, re.IGNORECASE)
    if first_tag_match:
        code = code[first_tag_match.start():]
    
    return code.strip()


def call_llm(prompt: str) -> str:
    """Call the LLM with the given prompt."""
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content


def create_vue_project_structure(output_dir: Path):
    """Create the base Vue 3 project structure with all necessary config files."""
    
    # Create directories
    (output_dir / "src" / "components").mkdir(parents=True, exist_ok=True)
    
    # package.json
    package_json = {
        "name": "translated-vue-app",
        "version": "1.0.0",
        "type": "module",
        "scripts": {
            "dev": "vite",
            "build": "vue-tsc && vite build",
            "preview": "vite preview",
            "typecheck": "vue-tsc --noEmit"
        },
        "dependencies": {
            "vue": "^3.5.0"
        },
        "devDependencies": {
            "typescript": "^5.7.0",
            "vite": "^6.0.0",
            "@vitejs/plugin-vue": "^5.2.0",
            "vue-tsc": "^2.2.0"
        }
    }
    (output_dir / "package.json").write_text(json.dumps(package_json, indent=2))
    
    # tsconfig.json
    tsconfig = {
        "compilerOptions": {
            "target": "ESNext",
            "module": "ESNext",
            "moduleResolution": "bundler",
            "strict": True,
            "jsx": "preserve",
            "sourceMap": True,
            "resolveJsonModule": True,
            "esModuleInterop": True,
            "skipLibCheck": True,
            "lib": ["ESNext", "DOM", "DOM.Iterable"]
        },
        "include": ["src/**/*.ts", "src/**/*.vue"]
    }
    (output_dir / "tsconfig.json").write_text(json.dumps(tsconfig, indent=2))
    
    # vite.config.ts
    vite_config = """import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()]
})
"""
    (output_dir / "vite.config.ts").write_text(vite_config)
    
    # index.html
    index_html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Vue App</title>
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/main.ts"></script>
</body>
</html>
"""
    (output_dir / "index.html").write_text(index_html)
    
    # src/main.ts
    main_ts = """import { createApp } from 'vue'
import App from './App.vue'

createApp(App).mount('#app')
"""
    (output_dir / "src" / "main.ts").write_text(main_ts)
    
    print(f"📁 Created Vue project structure in {output_dir}")


def js_to_component_name(js_filename: str) -> str:
    """Convert a JS filename to a PascalCase Vue component name."""
    # Remove extension and convert to PascalCase
    name = Path(js_filename).stem
    # Handle snake_case, kebab-case, etc.
    words = re.split(r'[-_\s]+', name)
    return ''.join(word.capitalize() for word in words)


def run_vue_validation(output_dir: Path, verbose: bool = True) -> tuple[bool, str]:
    """Validate the Vue project using vue-tsc."""
    result = subprocess.run(
        ["npx", "vue-tsc", "--noEmit", "-p", "tsconfig.json"],
        capture_output=True,
        text=True,
        cwd=output_dir
    )
    
    output = result.stdout + result.stderr
    
    if verbose:
        print("----- Vue Validation Result -----")
        if output.strip():
            print(output)
        print(f"EXIT CODE: {result.returncode}")
        print("---------------------------------")
    
    return result.returncode == 0, output


def translate_js_file(js_code: str, component_name: str) -> str:
    """Translate a single JS file to a Vue component."""
    prompt = f"""
Convert this Vanilla JavaScript into a modern Vue 3 Single File Component (.vue).

REQUIREMENTS:
1. Use <script setup lang="ts"> (Composition API).
2. Convert DOM manipulations into Vue reactivity (ref(), reactive(), computed()).
3. Convert event listeners to Vue template event bindings (@click, @input, etc.).
4. Include a functional <template> that reflects the original logic.
5. Use proper TypeScript types.
6. Import from 'vue' (e.g., import {{ ref }} from 'vue').
7. Return ONLY the .vue file content, no markdown.

CRITICAL - Common mistakes to avoid:
- Use v-model="variable" NOT v-model:value="variable" (v-model:value is INVALID syntax)
- Use ref<string>() NOT Ref<string> for type annotations on ref variables

COMPONENT NAME: {component_name}

SOURCE CODE:
{js_code}
"""
    vue_code = call_llm(prompt)
    return clean_llm_output(vue_code)


def repair_vue_code(vue_code: str, error_log: str) -> str:
    """Attempt to repair Vue code based on error log."""
    prompt = f"""
The following Vue 3 code has compilation/type errors.
Fix ALL errors while maintaining the logic. Return ONLY the corrected .vue code, no markdown.

CRITICAL - Common mistakes to fix:
- Use v-model="variable" NOT v-model:value="variable" (v-model:value is INVALID on plain elements)
- Ensure all imports are from 'vue' (not empty string)
- Use proper TypeScript types with ref<T>() syntax
- Use const for ref declarations, not let

ERRONEOUS CODE:
{vue_code}

ERROR LOG:
{error_log}
"""
    repaired = call_llm(prompt)
    return clean_llm_output(repaired)


def translate_project(input_dir: Path, output_dir: Path):
    """Main function to translate a vanilla JS project to Vue 3."""
    
    # Validate input directory
    if not input_dir.exists():
        print(f"❌ Error: Input directory '{input_dir}' does not exist.")
        sys.exit(1)
    
    # Find all JS files in input directory
    js_files = list(input_dir.glob("*.js"))
    if not js_files:
        print(f"❌ Error: No .js files found in '{input_dir}'")
        sys.exit(1)
    
    print(f"📂 Found {len(js_files)} JavaScript file(s) to translate:")
    for f in js_files:
        print(f"   - {f.name}")
    
    # Create output project structure
    if output_dir.exists():
        print(f"🗑️  Cleaning existing output directory: {output_dir}")
        shutil.rmtree(output_dir)
    
    create_vue_project_structure(output_dir)
    
    # Translate each JS file to a Vue component
    components = []
    for js_file in js_files:
        component_name = js_to_component_name(js_file.name)
        print(f"\n🔄 Translating {js_file.name} → {component_name}.vue")
        
        js_code = js_file.read_text()
        vue_code = translate_js_file(js_code, component_name)
        
        vue_file = output_dir / "src" / "components" / f"{component_name}.vue"
        vue_file.write_text(vue_code)
        components.append(component_name)
        print(f"   ✓ Created {vue_file.relative_to(output_dir)}")
    
    # Create App.vue that imports all components
    app_vue = generate_app_vue(components)
    (output_dir / "src" / "App.vue").write_text(app_vue)
    print(f"\n📝 Created src/App.vue with {len(components)} component(s)")
    
    # Install dependencies
    print("\n📦 Installing dependencies...")
    result = subprocess.run(
        ["npm", "install"],
        cwd=output_dir,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"⚠️  npm install warnings:\n{result.stderr}")
    else:
        print("   ✓ Dependencies installed")
    
    # Validate and repair loop
    print("\n🔍 Validating Vue project...")
    for attempt in range(MAX_RETRIES):
        is_valid, error_log = run_vue_validation(output_dir)
        
        if is_valid:
            print("✅ Success! Vue project passed validation.")
            break
        else:
            print(f"❌ Attempt {attempt + 1} failed. Repairing components...")
            
            # Parse errors to find which files need repair
            for component in components:
                component_file = output_dir / "src" / "components" / f"{component}.vue"
                if component in error_log or f"{component}.vue" in error_log:
                    vue_code = component_file.read_text()
                    repaired_code = repair_vue_code(vue_code, error_log)
                    component_file.write_text(repaired_code)
                    print(f"   🔧 Repaired {component}.vue")
            
            # Also check App.vue
            app_file = output_dir / "src" / "App.vue"
            if "App.vue" in error_log:
                vue_code = app_file.read_text()
                repaired_code = repair_vue_code(vue_code, error_log)
                app_file.write_text(repaired_code)
                print("   🔧 Repaired App.vue")
    else:
        print("⚠️  Max retries reached. Some errors may remain.")
    
    # Final summary
    print("\n" + "=" * 50)
    print("🎉 Translation Complete!")
    print("=" * 50)
    print(f"\nOutput directory: {output_dir.absolute()}")
    print("\nTo run the Vue project:")
    print(f"  cd {output_dir}")
    print("  npm run dev")
    print("\nTo build for production:")
    print(f"  cd {output_dir}")
    print("  npm run build")


def generate_app_vue(components: list[str]) -> str:
    """Generate App.vue that includes all translated components."""
    imports = "\n".join([f"import {c} from './components/{c}.vue'" for c in components])
    component_tags = "\n    ".join([f"<{c} />" for c in components])
    
    return f"""<template>
  <div id="app">
    <h1>Translated Vue App</h1>
    {component_tags}
  </div>
</template>

<script setup lang="ts">
{imports}
</script>

<style>
#app {{
  font-family: Arial, sans-serif;
  max-width: 800px;
  margin: 0 auto;
  padding: 20px;
}}
</style>
"""


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python js_to_vue_translator.py <input_dir> <output_dir>")
        print("Example: python js_to_vue_translator.py ./input ./output")
        sys.exit(1)
    
    input_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    
    translate_project(input_dir, output_dir)
