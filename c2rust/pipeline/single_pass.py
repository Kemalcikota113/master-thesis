"""Single-pass C->Rust translation pipeline (compile-only validation)."""

import json
from pathlib import Path

from c2rust import config
from c2rust.agents.translator_agent import (
    create_translator_agent,
    get_response_diagnostics,
    get_token_usage,
    translate_c_to_rust,
)
from c2rust.utils.fidelity import (
    analyze_rust_files_quality,
    compute_fidelity_report,
    export_fidelity_report,
    extract_c_public_api_functions,
    extract_c_defined_functions,
    extract_rust_functions,
)
from c2rust.utils.file_discovery import (
    build_header_context,
    discover_c_files,
    discover_header_files,
)
from c2rust.utils.metrics import MetricsCollector, TranslationMetrics
from c2rust.utils.rust_project import (
    relative_c_to_module_name,
    scaffold_rust_project,
    write_module_index,
    write_translated_file,
)
from c2rust.utils.validation import run_cargo_check


def run_single_pass(dataset_name: str, datasets_root: Path, output_root: Path) -> TranslationMetrics:
    """Run file-level translation and compile-only validation."""
    print("=" * 70)
    print("C2RUST SINGLE-PASS PIPELINE")
    print("=" * 70)

    metrics = MetricsCollector(dataset_name, "single")
    metrics.start_timer()

    dataset_path = datasets_root / dataset_name
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    print(f"\nDataset: {dataset_name}")
    print(f"Path: {dataset_path}")

    c_files = discover_c_files(dataset_path)
    header_files = discover_header_files(dataset_path)
    metrics.record_discovered_files(len(c_files))
    metrics.record_header_context_count(len(header_files))

    print(f"\nDiscovered C files: {len(c_files)}")
    print(f"Header files as context: {len(header_files)}")

    if not c_files:
        metrics.stop_timer()
        return metrics.compute_metrics(config.get_provider_name(), config.get_model_id(), False)

    output_dir = output_root / f"{dataset_name}-rust"
    scaffold_rust_project(output_dir, f"{dataset_name}-rust")

    model = config.get_model()
    agent = create_translator_agent(model)
    header_context = build_header_context(header_files)
    expected_c_functions = extract_c_public_api_functions(header_files)
    expected_source = "header_public_api"
    if not expected_c_functions:
        expected_c_functions = extract_c_defined_functions(c_files)
        expected_source = "c_defined_fallback"

    translated_modules: list[str] = []
    translated_files: list[Path] = []
    per_file_diagnostics: list[dict[str, object]] = []
    translation_diagnostics: dict[str, object] = {
        "mode": "one_shot",
        "translation_attempts_per_file": 1,
        "expected_function_source": expected_source,
        "files": per_file_diagnostics,
    }

    print("\nTranslating files...")
    print(f"Expected function source: {expected_source} ({len(expected_c_functions)} symbols)")
    for idx, (relative_path, absolute_path) in enumerate(c_files, start=1):
        print(f"  [{idx}/{len(c_files)}] {relative_path}")
        try:
            c_code = absolute_path.read_text(encoding="utf-8", errors="ignore")
            rust_code, response = translate_c_to_rust(
                agent=agent,
                c_code=c_code,
                file_path=relative_path,
                header_context=header_context,
                required_functions=expected_c_functions,
            )

            prompt_tokens, completion_tokens = get_token_usage(response)
            metrics.add_tokens(prompt_tokens, completion_tokens)
            response_diagnostics = get_response_diagnostics(response)

            module_name = relative_c_to_module_name(relative_path)
            output_path = write_translated_file(output_dir, module_name, rust_code)
            translated_modules.append(module_name)
            translated_files.append(output_path)

            per_file_diagnostics.append(
                {
                    "source_file": relative_path,
                    "output_module": module_name,
                    "output_file": str(output_path),
                    "prompt_chars": len(c_code) + len(header_context),
                    "output_chars": len(rust_code),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    **response_diagnostics,
                }
            )
            metrics.increment_files_translated()
        except Exception as exc:
            print(f"    Translation failed: {exc}")

    write_module_index(output_dir, translated_modules)

    rust_functions = extract_rust_functions(translated_files)
    placeholder_count, placeholder_hits, possible_truncation, truncation_reasons = analyze_rust_files_quality(
        translated_files
    )
    fidelity_report = compute_fidelity_report(
        expected_functions=expected_c_functions,
        rust_functions=rust_functions,
        min_strict_coverage=config.get_fidelity_min_strict_coverage(),
        min_relaxed_coverage=config.get_fidelity_min_relaxed_coverage(),
        gate_mode=config.get_fidelity_gate_mode(),
        placeholder_count=placeholder_count,
        placeholder_hits=placeholder_hits,
        possible_truncation=possible_truncation,
        truncation_reasons=truncation_reasons,
    )
    fidelity_report_path = output_dir / "fidelity_report.json"
    export_fidelity_report(fidelity_report, fidelity_report_path)
    metrics.record_fidelity_report(fidelity_report, fidelity_report_path)

    translation_diagnostics["placeholder_count"] = fidelity_report.placeholder_count
    translation_diagnostics["placeholder_hits"] = fidelity_report.placeholder_hits
    translation_diagnostics["possible_truncation"] = fidelity_report.possible_truncation
    translation_diagnostics["truncation_reasons"] = fidelity_report.truncation_reasons
    translation_diagnostics["fidelity_gate_mode"] = fidelity_report.gate_mode
    diagnostics_path = output_dir / "translation_diagnostics.json"
    diagnostics_path.write_text(json.dumps(translation_diagnostics, indent=2), encoding="utf-8")
    metrics.record_translation_diagnostics_path(diagnostics_path)

    print("\nFidelity gate")
    print(f"  Gate mode: {fidelity_report.gate_mode}")
    print(f"  Strict coverage: {fidelity_report.strict_coverage:.1%}")
    print(f"  Relaxed coverage: {fidelity_report.relaxed_coverage:.1%}")
    print(f"  Missing functions: {len(fidelity_report.missing_functions)}")
    print(f"  Placeholder count: {fidelity_report.placeholder_count}")
    print(f"  Possible truncation: {fidelity_report.possible_truncation}")
    print(f"  Gate passed: {fidelity_report.gate_passed}")

    if fidelity_report.placeholder_count > 0:
        reason = "pre-compile gate failed: forbidden placeholder patterns detected"
        print(f"\nSkipping compile check: {reason}")
        metrics.record_pre_compile_gate_failure(reason)
        translation_diagnostics["compile_skipped"] = True
        translation_diagnostics["compile_skipped_reason"] = reason
        diagnostics_path.write_text(json.dumps(translation_diagnostics, indent=2), encoding="utf-8")

        compile_output_path = output_dir / "compile_output.txt"
        compile_output_path.write_text(
            "Compile skipped because translation output contains forbidden placeholder patterns.\n"
            "See translation_diagnostics.json and fidelity_report.json for details.\n",
            encoding="utf-8",
        )
        metrics.record_compile_output_path(compile_output_path)
        metrics.record_initial_errors([])
        metrics.record_final_errors([])
        metrics.stop_timer()

        final_metrics = metrics.compute_metrics(
            config.get_provider_name(),
            config.get_model_id(),
            False,
        )
        metrics_path = output_dir / "metrics.json"
        MetricsCollector.export_to_json(final_metrics, metrics_path)

        print("\n" + "=" * 70)
        print("RESULT")
        print("=" * 70)
        print(f"Files translated: {final_metrics.files_translated}/{final_metrics.files_discovered}")
        print(f"Compile success: {final_metrics.compile_success}")
        print("Final compiler errors: skipped")
        print(f"Fidelity gate passed: {final_metrics.fidelity_gate_passed}")
        print(f"Strict symbol coverage: {final_metrics.fidelity_strict_coverage:.1%}")
        print(f"Placeholder count: {final_metrics.placeholder_count}")
        print(f"Possible truncation: {final_metrics.possible_truncation}")
        print(f"Tokens used: {final_metrics.tokens_used['total']:,}")
        print(f"Output: {output_dir}")
        print("=" * 70)

        return final_metrics

    print("\nRunning compile check (cargo check)...")
    validation = run_cargo_check(output_dir)

    compile_output_path = output_dir / "compile_output.txt"
    compile_output_path.write_text(validation.raw_output, encoding="utf-8")
    metrics.record_compile_output_path(compile_output_path)

    metrics.record_initial_errors(validation.errors)
    metrics.record_final_errors(validation.errors)
    metrics.stop_timer()

    final_metrics = metrics.compute_metrics(
        config.get_provider_name(),
        config.get_model_id(),
        validation.success,
    )

    metrics_path = output_dir / "metrics.json"
    MetricsCollector.export_to_json(final_metrics, metrics_path)

    print("\n" + "=" * 70)
    print("RESULT")
    print("=" * 70)
    print(f"Files translated: {final_metrics.files_translated}/{final_metrics.files_discovered}")
    print(f"Compile success: {final_metrics.compile_success}")
    print(f"Final compiler errors: {final_metrics.final_error_count}")
    print(f"Fidelity gate passed: {final_metrics.fidelity_gate_passed}")
    print(f"Strict symbol coverage: {final_metrics.fidelity_strict_coverage:.1%}")
    print(f"Placeholder count: {final_metrics.placeholder_count}")
    print(f"Possible truncation: {final_metrics.possible_truncation}")
    print(f"Tokens used: {final_metrics.tokens_used['total']:,}")
    print(f"Output: {output_dir}")
    print("=" * 70)

    return final_metrics
