# Pilot APR Report (C -> Rust, Compile-Level)

## Research Direction (Current)

- Scope was narrowed from runtime errors to compiler-level errors only.
- Core pipeline is now: `C project -> rough Rust translation -> fidelity gate -> APR loop`.
- Main thesis variable is APR context strategy (not translation strategy).
- Objective: measure how context granularity affects compile-error repair performance.

## Languages and Tooling

- Source language: `C`
- Target language: `Rust`
- Translation + APR model: `gpt-4o`
- Validation command: `cargo check` (compile-only)

## Dataset Preparation

- Added raw vs cleaned split under `datasets-c/raw-data` and `datasets-c/`.
- Raw datasets are used for reproducibility/health checks.
- Cleaned datasets are used for translation/APR (noise removed: tests/fuzz/build artifacts where needed).
- Cleaning decisions are documented in `datasets-c/cleaning.md`.

## Translation Stage Design (Fixed Baseline)

- One-shot file-level translation (no within-file chunking).
- `.c` files translated; `.h` used as context.
- Translation quality gate before APR:
  - relaxed symbol coverage threshold,
  - placeholder count must be `0`,
  - truncation flags must be false.
- Rationale: APR should repair compile errors on a sufficiently complete scaffold, not synthesize missing code.

## APR Experimental Setup

- 4 context strategies:
  1. error only
  2. error + target Rust file
  3. error + target Rust file + source C file
  4. error + target Rust file + source C file + related Rust context (bounded)
- Max attempts per strategy: `5`
- Iterative feedback loop: each attempt runs on previous repaired state.
- Fairness: each strategy starts from same translated snapshot.
- Outputs logged for analysis:
  - `runs.csv`, `summary.csv`, `attempts.csv`
  - per-attempt prompts/responses/compile logs in `artifacts/`

## Pilot Results So Far

### SDS (`experiments/20260301_205213`)

- Translation gate passed (`fidelity_relaxed_coverage = 1.0`), compile errors at APR start: `76`.
- APR after 5 attempts:
  - `error_only`: `76 -> 73` (reduction `3`)
  - `error_plus_rust`: `76 -> 68` (reduction `8`)
  - `error_rust_c`: `76 -> 68` (reduction `8`)
  - `error_rust_c_related`: `76 -> 68` (reduction `8`)

### HTTP Parser (`experiments/20260301_225307`)

- Translation gate passed (`fidelity_relaxed_coverage = 1.0`), compile errors at APR start: `58`.
- APR after 5 attempts:
  - `error_only`: `58 -> 40` (reduction `18`)
  - `error_plus_rust`: `58 -> 21` (reduction `37`)
  - `error_rust_c`: `58 -> 37` (reduction `21`)
  - `error_rust_c_related`: `58 -> 23` (reduction `35`)

### cJSON and kilo (`experiments/20260301_230827`)

- APR intentionally skipped due to translation gate failure.
- Rationale: keep APR comparison valid by excluding low-fidelity translation baselines.

## Key Interpretation

- Context helps, but effect is dataset-dependent.
- On SDS, all strategies plateau early after initial reductions.
- Recurrent blocker class on SDS is macro-related (`goto_*`) and variadic/C-interop style constructs.
- This suggests a strong next thesis-deepening path: focused handling of macro/low-level structural error families.

## Slide-Ready Explanation (Simple)

- A macro is a compiler-level code shortcut that expands into real code before normal type-checking.
- In translated SDS Rust, macro calls like `goto_cleanup!(...)` and `goto_err!(...)` are structurally inconsistent with their definitions.
- APR can fix easy local errors first, but when these macro structures are wrong, later attempts keep hitting the same blocker.
- Result: error count decreases early, then plateaus.

### Concrete Example from Current Pilot

- Dataset/Run: `sds-master`, experiment `20260301_205213`.
- Repeated macro blocker (attempt loop):
  - `error: cannot find macro 'goto_cleanup' in this scope`
  - file: `src/translated/sds.rs`, around line `677`
  - this repeatedly appears in `experiments/20260301_205213/attempts.csv`.
- Related compiler-level incompatibility in same file:
  - `error[E0658]: use of unstable library feature 'c_variadic'`
  - file: `src/translated/sds.rs`, around lines `402/444`
  - this is a concrete Rust compiler error code from the translated output.

## Why This Is a Valid Pilot

- End-to-end experimental system is implemented and reproducible.
- Translation quality is explicitly controlled before APR.
- APR comparison is controlled (same baseline, same model, same attempts).
- Data is ready for visualization and report writing.

## Plots

### SDS Plots (`experiments/20260301_205213/plots`)

![SDS Error Trajectory](experiments/20260301_205213/plots/error_trajectory.png)

![SDS Token Usage](experiments/20260301_205213/plots/token_usage.png)

![SDS Efficiency per 1K Tokens](experiments/20260301_205213/plots/efficiency_per_1k_tokens.png)

### HTTP Parser Plots (`experiments/20260301_225307/plots`)

![HTTP Parser Error Trajectory](experiments/20260301_225307/plots/error_trajectory.png)

![HTTP Parser Token Usage](experiments/20260301_225307/plots/token_usage.png)

![HTTP Parser Efficiency per 1K Tokens](experiments/20260301_225307/plots/efficiency_per_1k_tokens.png)

## Next Steps

- Run the same APR protocol on more translation-gate-passing datasets.
- Aggregate multi-dataset metrics into one comparative table/plot set.
- Add a focused macro/structural normalization step as a potential thesis extension and evaluate its effect.

### Scientific APR Architecture Extension for Macro Issues

1. **Error Family Detection Layer**
   - Parse compiler output and classify errors into families (`macro`, `variadic`, `unresolved symbol`, `type`, `syntax`).
   - Route macro-family errors to a dedicated repair path.

2. **Macro-Aware Preprocessor (Deterministic)**
   - Normalize/hoist `macro_rules!` blocks before usage.
   - Validate macro invocation arity against definition (argument-count checks).
   - Emit a normalized intermediate Rust file before LLM repair.

3. **Specialized APR Prompting by Error Family**
   - For macro-family attempts, constrain APR prompt to macro definitions + failing call sites + nearby function scopes.
   - For non-macro families, use existing context ladder (strategies 1-4).

4. **Verification Loop with Guardrails**
   - Compile after each patch.
   - Reject patches causing LOC/function collapse or regressions.
   - Track per-family repair success metrics.

5. **Evaluation Addition**
   - Compare baseline APR vs macro-aware APR on:
     - attempts-to-resolve macro-family errors,
     - total error reduction,
     - token efficiency,
     - final compile success rate.
