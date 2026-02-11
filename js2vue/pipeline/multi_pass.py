"""
Multi-pass translation pipeline with APRA feedback loop (experimental).

This pipeline:
1. Discovers and translates files (same as single-pass)
2. Validates with vue-tsc
3. Chunk-level repair: Fixes errors in individual files
4. Assembly-level repair: Fixes cross-component errors
5. Records iteration metrics for thesis analysis

This produces experimental data for RQ2 and RQ3 comparison.
"""

from pathlib import Path
from typing import List, Dict

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
from js2vue.utils.validation import run_vue_tsc, ValidationError
from js2vue.utils.metrics import MetricsCollector, TranslationMetrics


def run_multi_pass(dataset_name: str, datasets_root: Path, output_root: Path) -> TranslationMetrics:
    """
    Runs the multi-pass translation pipeline with APRA feedback loop.

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
    print("MULTI-PASS TRANSLATION PIPELINE (EXPERIMENTAL)")
    print("=" * 70)

    # Initialize metrics collector
    metrics = MetricsCollector(dataset_name, "multi")
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

    # Step 5: Translate each JavaScript file (same as single-pass)
    print(f"\n🔄 Translating files...")
    component_paths = []
    file_mapping = {}  # Maps relative_path -> output_path for repair

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

            # Determine output path
            output_path = preserve_directory_structure(relative_path, output_dir)

            # Write Vue file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(vue_code)

            # Track for App.vue and repair
            rel_to_src = output_path.relative_to(output_dir / "src")
            component_paths.append(str(rel_to_src.with_suffix('')))
            file_mapping[str(rel_to_src)] = output_path

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

    # Step 8: Initial validation
    print(f"\n✅ Running initial validation (vue-tsc)...")
    validation_result = run_vue_tsc(output_dir)
    metrics.record_initial_errors(validation_result.errors)

    initial_error_count = len(validation_result.errors)
    print(f"   Initial errors: {initial_error_count}")

    if initial_error_count == 0:
        print("   🎉 No errors! Skipping repair loops.")
        metrics.record_final_errors([])
        metrics.stop_timer()
        final_metrics = metrics.compute_metrics(
            config.get_provider_name(),
            config.get_model_id()
        )
        metrics_path = output_dir / "metrics.json"
        metrics.export_to_json(final_metrics, metrics_path)
        return final_metrics

    # Step 9: CHUNK-LEVEL REPAIR LOOP
    print(f"\n🔧 Starting chunk-level repair loop...")
    print(f"   Max iterations: {config.get_max_iterations()}")

    # Group errors by file
    errors_by_file = group_errors_by_file(validation_result.errors)
    print(f"   Files with errors: {len(errors_by_file)}")

    current_errors = initial_error_count

    for iteration in range(1, config.get_max_iterations() + 1):
        print(f"\n   Iteration {iteration}/{config.get_max_iterations()}")

        errors_before = current_errors
        files_fixed = 0

        for file_path, file_errors in errors_by_file.items():
            if not file_errors:
                continue

            print(f"      Repairing {file_path} ({len(file_errors)} errors)...")

            # Read current file content
            full_path = output_dir / "src" / file_path
            if not full_path.exists():
                continue

            with open(full_path, 'r', encoding='utf-8') as f:
                broken_code = f.read()

            # TODO: Invoke healer_agent (APRA)
            # This is where the APRA (Automatic Program Repair Agent) will be called
            # Once implemented in agents/healer_agent.py, replace this TODO with:
            #
            # from js2vue.agents.healer_agent import create_healer_agent, repair_vue_code
            # healer = create_healer_agent(model)
            # fixed_code = repair_vue_code(
            #     healer,
            #     broken_code=broken_code,
            #     errors=file_errors,
            #     file_path=file_path
            # )
            #
            # # Write fixed code
            # with open(full_path, 'w', encoding='utf-8') as f:
            #     f.write(fixed_code)
            #
            # files_fixed += 1

            # Placeholder: For now, no repair happens
            pass

        # Re-validate after chunk-level repairs
        # TODO: Uncomment when APRA is implemented
        # validation_result = run_vue_tsc(output_dir)
        # current_errors = len(validation_result.errors)
        # errors_after = current_errors
        #
        # # Record iteration metrics
        # metrics.record_repair_iteration(errors_before, errors_after)
        #
        # print(f"      Errors: {errors_before} → {errors_after} (Δ {errors_before - errors_after})")
        #
        # # Break if no improvement
        # if errors_after >= errors_before:
        #     print(f"      No improvement, stopping chunk-level repair")
        #     break
        #
        # # Break if all errors resolved
        # if errors_after == 0:
        #     print(f"      ✅ All errors resolved!")
        #     break
        #
        # # Update errors_by_file for next iteration
        # errors_by_file = group_errors_by_file(validation_result.errors)

        # Placeholder: Break after first iteration since no repair happens yet
        print(f"      ⚠️  APRA not implemented yet - skipping actual repair")
        break

    # Step 10: ASSEMBLY-LEVEL REPAIR LOOP
    print(f"\n🔧 Starting assembly-level repair loop...")
    print(f"   (Targets cross-component errors)")

    # TODO: Implement assembly-level repair
    # This loop handles errors that span multiple files, such as:
    # - Missing imports between components
    # - Type mismatches in component interfaces
    # - Prop passing errors
    #
    # for iteration in range(1, config.get_max_iterations() + 1):
    #     print(f"\n   Iteration {iteration}/{config.get_max_iterations()}")
    #
    #     validation_result = run_vue_tsc(output_dir)
    #     errors_before = len(validation_result.errors)
    #
    #     if errors_before == 0:
    #         break
    #
    #     # Group errors by type (e.g., missing imports, type mismatches)
    #     import_errors = [e for e in validation_result.errors
    #                      if e.category == ErrorCategory.MISSING_IMPORT]
    #
    #     # TODO: Invoke healer_agent with cross-component context
    #     # healer = create_healer_agent(model)
    #     # fixed_files = repair_cross_component_errors(
    #     #     healer,
    #     #     errors=import_errors,
    #     #     project_dir=output_dir
    #     # )
    #
    #     # Re-validate
    #     # validation_result = run_vue_tsc(output_dir)
    #     # errors_after = len(validation_result.errors)
    #     #
    #     # metrics.record_repair_iteration(errors_before, errors_after)
    #     #
    #     # if errors_after >= errors_before:
    #     #     break

    print(f"   ⚠️  APRA not implemented yet - skipping assembly-level repair")

    # Step 11: Final validation and metrics
    print(f"\n✅ Running final validation...")
    final_validation = run_vue_tsc(output_dir)
    metrics.record_final_errors(final_validation.errors)

    # Step 12: Display results
    print("\n" + "=" * 70)
    print("TRANSLATION COMPLETE")
    print("=" * 70)

    if final_validation.success:
        print("✅ No validation errors!")
    else:
        print(f"⚠️  Final validation: {len(final_validation.errors)} errors")
        print("\nError breakdown:")

        from js2vue.utils.validation import ErrorCategory
        category_counts = {}
        for error in final_validation.errors:
            category_counts[error.category] = category_counts.get(error.category, 0) + 1

        for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"   {category.value}: {count}")

        print("\nFirst 5 errors:")
        for error in final_validation.errors[:5]:
            print(f"   {error.file}:{error.line} - {error.message[:80]}")

    # Step 13: Compute and export metrics
    metrics.stop_timer()
    final_metrics = metrics.compute_metrics(
        config.get_provider_name(),
        config.get_model_id()
    )

    metrics_path = output_dir / "metrics.json"
    metrics.export_to_json(final_metrics, metrics_path)

    # Step 14: Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Files translated: {final_metrics.files_translated}")
    print(f"Initial errors: {final_metrics.initial_error_count}")
    print(f"Final errors: {final_metrics.final_error_count}")
    print(f"Error reduction: {final_metrics.initial_error_count - final_metrics.final_error_count}")
    if final_metrics.error_reduction_factor != float('inf'):
        print(f"Error reduction factor: {final_metrics.error_reduction_factor:.2f}x")
    print(f"Repair iterations: {final_metrics.repair_iterations}")
    print(f"Template-script coherence errors: {final_metrics.template_script_coherence_errors}")
    print(f"Tokens used: {final_metrics.tokens_used['total']:,}")
    print(f"Time: {final_metrics.timing_seconds:.1f}s")
    print(f"Output: {output_dir}")
    print("=" * 70)

    return final_metrics


def group_errors_by_file(errors: List[ValidationError]) -> Dict[str, List[ValidationError]]:
    """
    Groups validation errors by file path.

    Args:
        errors: List of validation errors

    Returns:
        Dictionary mapping file paths to lists of errors
    """
    errors_by_file = {}

    for error in errors:
        file_path = error.file
        if file_path not in errors_by_file:
            errors_by_file[file_path] = []
        errors_by_file[file_path].append(error)

    return errors_by_file
