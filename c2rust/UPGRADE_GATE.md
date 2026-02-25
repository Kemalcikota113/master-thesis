# Upgrade Gate: Step 1 -> Step 2

This project starts with:

- Step 1: translate `.c` files only, use `.h` files as context.

Move to Step 2 (translate `.h` too) only when all criteria below are met for at least 2 datasets.

## Gate Criteria

1. Pipeline Stability
- End-to-end runs complete without manual intervention.
- `metrics.json` and `compile_output.txt` are produced for every run.

2. Diagnostic Quality
- At least 80% of compiler errors are parsed with a file and line number.
- Error categories show usable diversity (not dominated by parser failures only).

3. Baseline Reproducibility
- Re-running the same dataset with same config yields same compile success state.
- Error count variance across reruns stays within a small tolerance.

4. APR Readiness
- Context policy comparisons are implementable on the current artifact format.
- Token/time logging is stable enough for cost-quality analysis.

## Why Gate First

Translating headers introduces extra confounders (macro expansion patterns, duplicate interface mappings, module wiring complexity). Step 1 isolates the core translation + compile feedback loop before adding that complexity.
