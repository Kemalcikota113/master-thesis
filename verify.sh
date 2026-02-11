#!/bin/bash
source venv/bin/activate

echo "=== JS2Vue v1 Verification ==="
echo ""

echo "1. Module imports..."
python3 -c "import js2vue.config; import js2vue.translate; print('✅ All modules import successfully')" || exit 1

echo ""
echo "2. CLI help..."
python3 -m js2vue.translate --help > /dev/null && echo "✅ CLI functional" || exit 1

echo ""
echo "3. File discovery..."
python3 -c "from js2vue.utils.file_discovery import discover_js_files; files=discover_js_files('datasets/todomvc-es6'); print(f'✅ Discovered {len(files)} files')" || exit 1

echo ""
echo "4. Configuration..."
python3 -c "from js2vue import config; print(f'✅ Provider: {config.get_provider_name()}, Model: {config.get_model_id()}')" || exit 1

echo ""
echo "=== All verification checks passed! ==="
echo ""
echo "⚠️  Note: End-to-end translation requires valid API keys"
echo "Run: python3 -m js2vue.translate todomvc-es6 --mode single"
