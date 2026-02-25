# c2rust MVP Scaffold

Minimal file-level C to Rust translation scaffold for compile-only experiments.

## Scope (current)

- Single-pass translation only
- Input translation from `.c` files only
- `.h` files included as prompt context only
- Validation via `cargo check` only
- Fidelity gate (symbol coverage) before APR
- Placeholder count must be 0 before APR
- One-shot translation per file (single attempt)
- Fidelity baseline prefers public function declarations from headers
- Compile is skipped when forbidden placeholder markers are detected
- Baseline gate mode uses relaxed symbol matching by default

## Run

```bash
python -m c2rust.translate sds-master
```

Optional overrides:

```bash
python -m c2rust.translate sds-master --provider gemini --model gemini-2.0-flash-exp
```

## Output

Pipeline output is written to:

`output/<dataset>-rust/`

- `Cargo.toml`
- `src/lib.rs`
- `src/translated/*.rs`
- `compile_output.txt`
- `metrics.json`
- `fidelity_report.json`
- `translation_diagnostics.json`

See `c2rust/PROMPT_CONTRACT.md` for exact translation-stage rules.

## APR Positioning

APR should start only after the translation fidelity report is acceptable.
If compile passes but fidelity is low, treat the run as translation failure (incomplete translation), not APR success.
