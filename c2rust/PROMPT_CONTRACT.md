# Translation Prompt Contract

This contract defines the translation-stage objective before APR.

## Stage Separation

1. Translation stage: one-shot full-code translation.
2. APR stage: compiler-error repair after translation gate passes.

## Translation Rules

- One model call per source file (no retries, no completion loop).
- Preserve full function coverage from C source.
- Do not omit functions to make code compile.
- Do not use placeholders/stubs (no `TODO`, `unimplemented!`, dummy bodies).
- Best-effort concrete implementation is required, even if compilation fails.

## Gate Requirements

- Symbol coverage must meet configured threshold (strict or relaxed mode).
- Placeholder count must be zero.
- No truncation signals.

## Fail-Fast Behavior

- If forbidden placeholder markers are detected, compile is skipped.
- Run is marked as translation failure before compiler-stage APR input.

If any gate check fails, translation is marked as failed and APR is skipped.
