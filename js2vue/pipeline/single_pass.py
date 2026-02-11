"""
Single-pass translation pipeline (baseline for thesis comparison).

This pipeline:
1. Discovers JavaScript files
2. Scaffolds a Vue 3 project
3. Translates each file once (no repair)
4. Validates with vue-tsc
5. Reports errors without attempting fixes

This produces baseline data for RQ2 comparison.
"""

from pathlib import Path
from typing import List

from js2vue import config
from js2vue.agents.translator_agent import (
    create_translator_agent,
    translate_js_to_vue,
    get_token_usage
)
from js2vue.utils.file_discovery import discover_js_files, get_component_name
from js2vue.utils.vue_project import (
    scaffold_vue_project,
    generate_app_vue,
    run_npm_install,
    preserve_directory_structure
)
from js2vue.utils.validation import run_vue_tsc, count_template_script_coherence_errors
from js2vue.utils.metrics import MetricsCollector, TranslationMetrics


def run_single_pass(dataset_name: str, datasets_root: Path, output_root: Path) -> TranslationMetrics:
    """
    Runs the single-pass translation pipeline (baseline).

    Args:
        dataset_name: Name of the dataset to translate
        datasets_root: Root directory containing datasets
        output_root: Root directory for output projects

    Returns:
        TranslationMetrics object with results

    Raises:
        FileNotFoundError: If dataset doesn't exist
        RuntimeError: If critical steps fail
    """
    print("=" * 70)
    print("SINGLE-PASS TRANSLATION PIPELINE (BASELINE)")
    print("=" * 70)

    # Initialize metrics collector
    metrics = MetricsCollector(dataset_name, "single")
    metrics.start_timer()

    # Step 1: Validate dataset exists
    dataset_path = datasets_root / dataset_name
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    print(f"\n📁 Dataset: {dataset_name}")
    print(f"   Path: {dataset_path}")

    # Step 2: Discover JavaScript files
    print(f"\n🔍 Discovering JavaScript files...")
    js_files = discover_js_files(dataset_path)

    if not js_files:
        print("⚠️  No JavaScript files found")
        metrics.stop_timer()
        return metrics.compute_metrics(
            config.get_provider_name(),
            config.get_model_id()
        )

    print(f"   Found {len(js_files)} JavaScript files")

    # Step 3: Scaffold Vue 3 project
    output_dir = output_root / f"{dataset_name}-vue"
    project_name = f"{dataset_name}-vue"

    print(f"\n🏗️  Scaffolding Vue 3 project...")
    scaffold_vue_project(output_dir, project_name)

    # Step 4: Initialize translator agent
    print(f"\n🤖 Initializing translator agent...")
    print(f"   Provider: {config.get_provider_name()}")
    print(f"   Model: {config.get_model_id()}")

    model = config.get_model()
    agent = create_translator_agent(model)

    # Step 5: Translate each JavaScript file
    print(f"\n🔄 Translating files...")
    component_paths = []

    for idx, (relative_path, absolute_path) in enumerate(js_files, 1):
        print(f"   [{idx}/{len(js_files)}] {relative_path}")

        # Read JavaScript code
        with open(absolute_path, 'r', encoding='utf-8') as f:
            js_code = f.read()

        # Get component name
        component_name = get_component_name(relative_path)

        # Translate
        try:
            response = agent.run(
                f"""Translate the following JavaScript code to a Vue 3 SFC component.

Component Name: {component_name}
Original File: {relative_path}

JavaScript Code:
```javascript
{js_code}
```

Output the complete Vue 3 SFC with TypeScript."""
            )

            # Extract Vue code
            from js2vue.utils.code_cleaning import clean_llm_output
            if hasattr(response, 'content'):
                vue_code = response.content
            else:
                vue_code = str(response)

            vue_code = clean_llm_output(vue_code)

            # Track token usage
            prompt_tokens, completion_tokens = get_token_usage(response)
            metrics.add_tokens(prompt_tokens, completion_tokens)

            # Determine output path (preserve directory structure)
            output_path = preserve_directory_structure(relative_path, output_dir)

            # Write Vue file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(vue_code)

            # Track component for App.vue
            # Get path relative to src/
            rel_to_src = output_path.relative_to(output_dir / "src")
            component_paths.append(str(rel_to_src.with_suffix('')))

            metrics.increment_files_translated()

        except Exception as e:
            print(f"      ❌ Translation failed: {e}")
            continue

    # Step 6: Generate App.vue
    print(f"\n📝 Generating App.vue...")
    generate_app_vue(output_dir, component_paths)

    # Step 7: Run npm install
    print(f"\n📦 Installing dependencies...")
    if not run_npm_install(output_dir):
        raise RuntimeError("npm install failed")

    # Step 8: Run validation
    print(f"\n✅ Running type validation (vue-tsc)...")
    validation_result = run_vue_tsc(output_dir)

    # Step 9: Record errors (no repair in single-pass)
    metrics.record_initial_errors(validation_result.errors)
    metrics.record_final_errors(validation_result.errors)  # Same as initial

    # Step 10: Display results
    print("\n" + "=" * 70)
    print("TRANSLATION COMPLETE")
    print("=" * 70)

    if validation_result.success:
        print("✅ No validation errors!")
    else:
        print(f"⚠️  Validation found {len(validation_result.errors)} errors")
        print("\nError breakdown:")

        # Group by category
        from js2vue.utils.validation import ErrorCategory
        category_counts = {}
        for error in validation_result.errors:
            category_counts[error.category] = category_counts.get(error.category, 0) + 1

        for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"   {category.value}: {count}")

        # Show first few errors
        print("\nFirst 5 errors:")
        for error in validation_result.errors[:5]:
            print(f"   {error.file}:{error.line} - {error.message[:80]}")

    # Step 11: Compute and export metrics
    metrics.stop_timer()
    final_metrics = metrics.compute_metrics(
        config.get_provider_name(),
        config.get_model_id()
    )

    metrics_path = output_dir / "metrics.json"
    metrics.export_to_json(final_metrics, metrics_path)

    # Step 12: Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Files translated: {final_metrics.files_translated}")
    print(f"Validation errors: {final_metrics.final_error_count}")
    print(f"Template-script coherence errors: {final_metrics.template_script_coherence_errors}")
    print(f"Tokens used: {final_metrics.tokens_used['total']:,}")
    print(f"Time: {final_metrics.timing_seconds:.1f}s")
    print(f"Output: {output_dir}")
    print("=" * 70)

    return final_metrics
