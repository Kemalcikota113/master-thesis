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
from datetime import datetime

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
from js2vue.utils.validation import run_vue_tsc, ValidationError, run_runtime_validation
from js2vue.utils.metrics import MetricsCollector, TranslationMetrics
from js2vue.agents.runner_agent import RunnerAgent


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

    # Step 8: Comprehensive Validation (Static + Runtime + Error Analysis)
    print(f"\n✅ Running comprehensive validation...")

    # 8a. Static validation (existing)
    print(f"   Running static validation (vue-tsc)...")
    static_validation = run_vue_tsc(output_dir)
    print(f"   Static errors: {len(static_validation.errors)}")

    # 8b. Runtime validation (NEW)
    runtime_errors = []
    if config.get_runtime_capture_enabled():
        capture_duration = config.get_runtime_capture_duration()
        print(f"   Starting runtime error capture ({capture_duration}s)...")
        try:
            from js2vue.utils.runtime_capture import capture_runtime_errors
            import asyncio
            runtime_errors = asyncio.run(
                capture_runtime_errors(output_dir, config.get_vite_port(), capture_duration)
            )
            print(f"   Runtime errors: {len(runtime_errors)}")
        except Exception as e:
            print(f"   ⚠️  Runtime capture failed: {e}")
            runtime_errors = []
    else:
        print(f"   Runtime error capture disabled (use --runtime-duration to enable)")

    # Record errors in metrics
    metrics.record_initial_errors(static_validation.errors)
    metrics.record_runtime_errors(runtime_errors)

    initial_static_count = len(static_validation.errors)
    initial_runtime_count = len(runtime_errors)
    initial_error_count = initial_static_count + initial_runtime_count

    print(f"   Total errors: {initial_error_count} ({initial_static_count} static + {initial_runtime_count} runtime)")

    # 8c. Create logs directory for research artifacts
    logs_dir = output_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    print(f"\n📁 Logs directory created: {logs_dir}")

    # Open repair log file for detailed tracking
    repair_log_path = logs_dir / "repair_log.txt"
    repair_log = open(repair_log_path, 'w', encoding='utf-8')

    def log_and_print(message: str):
        """Helper to log to both console and file."""
        print(message)
        repair_log.write(message + '\n')
        repair_log.flush()

    log_and_print(f"\n🤖 Analyzing errors with Runner Agent...")

    # 8d. Run error analysis with Runner Agent
    runner_agent = RunnerAgent(model)
    error_report = runner_agent.categorize_errors(
        static_errors=static_validation.errors,
        runtime_errors=runtime_errors,
        npm_errors=[]  # TODO: capture from npm install
    )

    # Save initial error report with timestamp
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    initial_report_path = logs_dir / f"error_report_initial_{timestamp}.md"
    with open(initial_report_path, 'w') as f:
        f.write(error_report.to_markdown())
    log_and_print(f"   Error report saved: {initial_report_path}")

    # Also save to root for backwards compatibility
    root_report_path = output_dir / "error_report.md"
    with open(root_report_path, 'w') as f:
        f.write(error_report.to_markdown())

    # Record error report in metrics
    metrics.record_error_report(initial_report_path, analysis_tokens=0)  # TODO: track actual token usage

    if initial_error_count == 0:
        log_and_print("   🎉 No errors! Skipping repair loops.")
        repair_log.close()
        metrics.record_final_errors([])
        metrics.stop_timer()
        final_metrics = metrics.compute_metrics(
            config.get_provider_name(),
            config.get_model_id()
        )
        metrics_path = output_dir / "metrics.json"
        metrics.export_to_json(final_metrics, metrics_path)

        # Save to logs as well
        logs_metrics_path = logs_dir / f"metrics_final_{timestamp}.json"
        metrics.export_to_json(final_metrics, logs_metrics_path)

        return final_metrics

    # Store validation result for repair loop
    validation_result = static_validation

    # Step 9: APRA REPAIR LOOP (Automatic Program Repair Agent)
    log_and_print(f"\n🔧 Starting automatic repair loop with APRA...")
    log_and_print(f"   Max iterations: {config.get_max_iterations()}")

    # Import healer agent
    from js2vue.agents.healer_agent import create_healer_agent, repair_vue_file, load_original_js
    from js2vue.utils.metrics import RepairHistory, RepairAttempt

    # Initialize APRA agent
    healer_agent = create_healer_agent(model)
    repair_history = RepairHistory()

    current_static_errors = initial_static_count
    current_runtime_errors = initial_runtime_count
    current_error_report = error_report

    for iteration in range(1, config.get_max_iterations() + 1):
        iter_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_and_print(f"\n   === Iteration {iteration}/{config.get_max_iterations()} ===")
        log_and_print(f"   Timestamp: {iter_timestamp}")

        errors_before_total = current_static_errors + current_runtime_errors
        files_modified = []
        error_ids_targeted = []

        # Repair errors by priority (CRITICAL and HIGH first)
        priority_errors = [e for e in current_error_report.errors
                          if e.priority in ['CRITICAL', 'HIGH']]

        if not priority_errors:
            # If no critical/high, try medium priority
            priority_errors = [e for e in current_error_report.errors
                             if e.priority == 'MEDIUM']

        log_and_print(f"   Targeting {len(priority_errors)} errors ({', '.join(set(e.priority for e in priority_errors))} priority)")

        for error_entry in priority_errors:
            file_path = error_entry.source_error.file

            # Build full path
            if file_path.startswith('src/'):
                full_path = output_dir / file_path
            else:
                full_path = output_dir / "src" / file_path

            if not full_path.exists():
                log_and_print(f"      ⚠️  File not found: {file_path}")
                continue

            # Read current broken code
            with open(full_path, 'r', encoding='utf-8') as f:
                broken_code = f.read()

            # Get previous attempts for this file (from repair history)
            previous_attempts = [a for a in repair_history.attempts
                               if str(full_path) in a.files_modified]

            # Load original JavaScript for context
            original_js_code = load_original_js(
                datasets_root=datasets_root,
                dataset_name=dataset_name,
                vue_file_path=file_path
            )

            log_and_print(f"      Repairing {file_path} ({error_entry.priority}: {error_entry.category})...")

            # Run APRA repair
            try:
                fixed_code = repair_vue_file(
                    healer_agent=healer_agent,
                    broken_code=broken_code,
                    error_entry=error_entry,
                    file_path=file_path,
                    original_js_code=original_js_code,
                    previous_attempts=previous_attempts
                )

                # Write fixed code
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(fixed_code)

                files_modified.append(str(full_path))
                error_ids_targeted.append(error_entry.error_id)

            except Exception as e:
                log_and_print(f"         ⚠️  Repair failed: {e}")
                continue

        # Re-validate (static + runtime)
        log_and_print(f"\n   Re-validating (static + runtime)...")

        # Static validation
        new_static_validation = run_vue_tsc(output_dir)
        errors_after_static = len(new_static_validation.errors)

        # Runtime validation (if enabled)
        new_runtime_errors = []
        if config.get_runtime_capture_enabled():
            capture_duration = config.get_runtime_capture_duration()
            log_and_print(f"      Running runtime capture ({capture_duration}s)...")
            try:
                from js2vue.utils.runtime_capture import capture_runtime_errors
                import asyncio
                new_runtime_errors = asyncio.run(
                    capture_runtime_errors(output_dir, config.get_vite_port(), capture_duration)
                )
            except Exception as e:
                log_and_print(f"         ⚠️  Runtime capture failed: {e}")
                new_runtime_errors = []

        errors_after_runtime = len(new_runtime_errors)
        errors_after_total = errors_after_static + errors_after_runtime

        log_and_print(f"      Errors: {errors_before_total} → {errors_after_total}")
        log_and_print(f"         Static: {current_static_errors} → {errors_after_static}")
        log_and_print(f"         Runtime: {current_runtime_errors} → {errors_after_runtime}")

        # Record repair attempt
        attempt = RepairAttempt(
            iteration=iteration,
            files_modified=files_modified,
            error_ids_targeted=error_ids_targeted,
            repair_strategy=f"Priority-based repair ({len(priority_errors)} errors targeted)",
            errors_before=current_static_errors,
            errors_after=errors_after_static,
            runtime_errors_before=current_runtime_errors,
            runtime_errors_after=errors_after_runtime,
            success=errors_after_total < errors_before_total,
            timestamp=datetime.now().isoformat()
        )
        repair_history.attempts.append(attempt)

        # Save iteration-specific artifacts to logs/
        iteration_report_path = logs_dir / f"error_report_iter_{iteration}_{iter_timestamp}.md"
        if errors_after_total > 0:
            # Re-analyze errors for this iteration
            iter_error_report = runner_agent.categorize_errors(
                static_errors=new_static_validation.errors,
                runtime_errors=new_runtime_errors,
                npm_errors=[]
            )
            with open(iteration_report_path, 'w') as f:
                f.write(iter_error_report.to_markdown())
            log_and_print(f"      Error report saved: {iteration_report_path}")
        else:
            # No errors, create empty report
            with open(iteration_report_path, 'w') as f:
                f.write(f"# Error Report - Iteration {iteration}\n\n✅ All errors resolved!")

        # Save iteration metrics snapshot
        iteration_metrics_path = logs_dir / f"metrics_iter_{iteration}_{iter_timestamp}.json"
        interim_metrics = metrics.compute_metrics(
            config.get_provider_name(),
            config.get_model_id()
        )
        metrics.export_to_json(interim_metrics, iteration_metrics_path)

        # Record in metrics
        metrics.record_repair_iteration(errors_before_total, errors_after_total)

        # Check stopping conditions
        if errors_after_total == 0:
            log_and_print(f"      ✅ All errors resolved!")
            break

        if errors_after_total >= errors_before_total:
            log_and_print(f"      ⚠️  No progress made (or new errors introduced), stopping iteration")
            break

        # Update for next iteration
        current_static_errors = errors_after_static
        current_runtime_errors = errors_after_runtime

        # Re-run Runner Agent to analyze remaining errors
        if iteration < config.get_max_iterations():
            log_and_print(f"\n   Re-analyzing remaining errors...")
            current_error_report = runner_agent.categorize_errors(
                static_errors=new_static_validation.errors,
                runtime_errors=new_runtime_errors,
                npm_errors=[]
            )

    # Store repair history in metrics (will be exported to JSON)
    metrics.repair_history = repair_history

    log_and_print(f"\n   Repair loop complete. {len(repair_history.attempts)} iteration(s) executed.")

    # Close repair log
    repair_log.close()

    # Step 10: Final validation and metrics
    print(f"\n✅ Running final validation...")
    final_validation = run_vue_tsc(output_dir)
    metrics.record_final_errors(final_validation.errors)

    # Step 11: Display results
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

    # Step 12: Compute and export metrics
    metrics.stop_timer()
    final_metrics = metrics.compute_metrics(
        config.get_provider_name(),
        config.get_model_id()
    )

    # Save final metrics to root (for backwards compatibility)
    metrics_path = output_dir / "metrics.json"
    metrics.export_to_json(final_metrics, metrics_path)

    # Save final metrics to logs/ with timestamp
    final_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logs_metrics_path = logs_dir / f"metrics_final_{final_timestamp}.json"
    metrics.export_to_json(final_metrics, logs_metrics_path)

    # Save final error report to logs/
    final_error_report_path = logs_dir / f"error_report_final_{final_timestamp}.md"
    final_error_report = runner_agent.categorize_errors(
        static_errors=final_validation.errors,
        runtime_errors=[],  # Runtime errors not re-captured in final validation
        npm_errors=[]
    )
    with open(final_error_report_path, 'w') as f:
        f.write(final_error_report.to_markdown())

    # Step 13: Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Files translated: {final_metrics.files_translated}")
    print(f"Initial errors: {final_metrics.initial_error_count}")
    print(f"  - Static: {final_metrics.initial_error_count - final_metrics.runtime_errors}")
    print(f"  - Runtime: {final_metrics.runtime_errors}")
    if final_metrics.runtime_error_categories:
        for error_type, count in final_metrics.runtime_error_categories.items():
            print(f"    · {error_type}: {count}")
    print(f"Final errors: {final_metrics.final_error_count}")
    print(f"Error reduction: {final_metrics.initial_error_count - final_metrics.final_error_count}")
    if final_metrics.error_reduction_factor != float('inf'):
        print(f"Error reduction factor: {final_metrics.error_reduction_factor:.2f}x")
    print(f"Repair iterations: {final_metrics.repair_iterations}")
    print(f"Template-script coherence errors: {final_metrics.template_script_coherence_errors}")
    print(f"Tokens used: {final_metrics.tokens_used['total']:,}")
    print(f"Time: {final_metrics.timing_seconds:.1f}s")
    print(f"\nOutput directory: {output_dir}")
    print(f"\n📁 Research Artifacts:")
    print(f"   Repair log: {repair_log_path}")
    print(f"   Logs directory: {logs_dir}")
    print(f"   - Initial error report: {initial_report_path.name}")
    print(f"   - Final error report: {final_error_report_path.name}")
    print(f"   - Iteration reports: error_report_iter_N_*.md")
    print(f"   - Iteration metrics: metrics_iter_N_*.json")
    print(f"   - Final metrics: {logs_metrics_path.name}")
    print(f"\n💡 Quick access:")
    print(f"   Main metrics: {metrics_path}")
    print(f"   Main error report: {root_report_path}")
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
