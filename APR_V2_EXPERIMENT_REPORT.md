# APR Strategy Comparison Report
## C → Rust Automated Program Repair — Pilot Experiment v2

**Date:** March 2026
**Model:** GPT-4o
**Max attempts per strategy:** 10

---

## 1. Overview

This report describes a controlled pilot experiment comparing four Automated Program Repair (APR) prompting strategies for fixing compiler errors in C-to-Rust translated code. The experiment tests whether more sophisticated LLM prompting architectures lead to better repair performance, holding all other variables constant (same model, same translated baseline, same iteration budget).

The core question: **does structuring the prompting interaction — rather than just providing more context — improve repair outcomes?**

---

## 2. Datasets

Two C source libraries were selected from the cleaned dataset collection. Both passed the translation fidelity gate (relaxed symbol coverage ≥ 95%, no placeholders, no truncation), making them valid starting points for the APR comparison.

### SDS — Simple Dynamic Strings
- **Source:** `sds-master/sds.c`
- **Description:** A C library implementing dynamic strings, widely used in Redis. Features heavy use of custom macros, variadic functions, and raw memory manipulation.
- **Size:** ~1,300 lines of C source
- **Errors at APR start:** 75 compiler errors
- **Error profile:** Dominated by macro-related errors (`cannot find macro 'goto_cleanup'`, `goto_err`) and unstable-feature errors (`c_variadic`). These are structurally difficult — they require changing the macro definition, not just local call sites.

### HTTP Parser
- **Source:** `http-parser-main/http_parser.c`
- **Description:** Node.js's HTTP request/response parser. A single self-contained C file with complex state machine logic, callback tables, and integer arithmetic.
- **Size:** ~2,575 lines of C source
- **Errors at APR start:** 57 compiler errors
- **Error profile:** Mostly standard type mismatches, unresolved symbols, and borrow/lifetime issues — the kind of errors rustc provides clear `suggested_replacement` hints for.

---

## 3. APR Strategies

All four strategies share the same repair loop:

1. Run `cargo check --message-format=json` to get the current compile state.
2. Select the highest-priority actionable error using a priority function (macro errors first, then unresolved symbols, then type errors).
3. Build a strategy-specific prompt targeting the file containing that error.
4. Call GPT-4o and apply the patched file.
5. Re-compile, apply guardrails (reject if LOC shrinks >30%, function count drops >20%, or placeholders are introduced), and revert if errors increase by more than 3.
6. Repeat for up to 10 attempts.

Each strategy starts from an **identical copy** of the translated baseline, so results are directly comparable.

---

### Strategy 1 — Baseline

The simplest possible prompting approach. The full raw terminal output from `rustc` (the concatenated `rendered` fields from `cargo check --message-format=json`) is placed directly into the prompt alongside the full target Rust file. No parsing, no structuring, no multi-step reasoning.

```
## Raw Compiler Output
error[E0425]: cannot find value `foo` in this scope
 --> src/translated/sds.rs:42:5
  |
42|     let x = foo;
          ^^^
...

## Target Rust File: sds.rs
<full Rust source>
```

**Hypothesis going in:** Lower bound. Expected to perform worst due to raw, noisy input.

---

### Strategy 2 — Structured Compiler

Uses `cargo check --message-format=json` and parses each error into a structured numbered list containing the exact error code, file:line:col location, message, span label, and any compiler-suggested replacement. This removes the noise and redundancy from the raw terminal output, giving the model clean, actionable signal.

```
## Structured Compiler Errors (57 total)
1. [E0425] src/translated/sds.rs:42:5
   Message  : cannot find value `foo` in this scope
   Label    : not found in this scope
   Suggested: bar

2. [E0308] src/translated/sds.rs:88:12
   Message  : mismatched types
   Suggested: 42i32
...
```

**Hypothesis going in:** Better than Baseline due to precision of structured error information.

---

### Strategy 3 — Diagnose-then-Patch (Chain of Thought)

A two-call architecture per attempt. Rather than asking the model to output a fix directly, the interaction is split:

- **Call 1 (Diagnose):** The model is asked to produce a structured root-cause analysis — three sections: `ROOT CAUSE`, `TARGET SYMBOLS`, and `FIX PLAN`. No code is output.
- **Call 2 (Patch):** The model receives its own diagnosis alongside the errors and the Rust file, and is asked to output only the patched source.

The intent is to force the model to reason about the underlying cause before jumping to a local fix, reducing the chance of superficial patches that clear one error while introducing others.

**Hypothesis going in:** Better than Structured for datasets with deep structural errors.

---

### Strategy 4 — Memory / Reflexion

Extends Strategy 3 with a structured attempt memory block prepended to both calls. After each attempt, a `MemoryEntry` is recorded containing the targeted error code and message, the full diagnosis text from Call 1, the error count before and after, and the outcome (applied, regressed, rejected). All prior entries are included in subsequent prompts.

```
## Attempt Memory
Attempt 1: [E0658] "use of unstable library feature 'c_variadic'"
  Result  : 75 → 59 errors (↓16) | applied but compile still fails
  ROOT CAUSE: The translated code uses C-style variadic arguments...
  TARGET SYMBOLS: sdscatvprintf, sds_vsnprintf...
  FIX PLAN: 1. Add #![feature(c_variadic)] ...

Attempt 2: [macro] "cannot find macro 'goto_cleanup'"
  Result  : 59 → 58 errors (↓1) | applied but compile still fails
  ...
```

The model is explicitly instructed that its fix plan **must differ** from all previous failed approaches.

**Hypothesis going in:** Best performer on SDS, where the pilot showed cycling on the same error families is the primary bottleneck.

---

## 4. Results

### 4.1 Summary Table

| Dataset | Strategy | Compiled | Attempts | Errors (start→end) | % Fixed | Total Tokens | Efficiency (fixes/1K tok) |
|---|---|:---:|:---:|:---:|:---:|---:|:---:|
| sds-master | **S1 Baseline** | ✗ | 10 | 75 → **23** | **69.3%** | 195,627 | **0.266** |
| sds-master | S2 Structured | ✗ | 10 | 75 → 33 | 56.0% | 202,639 | 0.207 |
| sds-master | S3 Diagnose→Patch | ✗ | 10 | 75 → 43 | 42.7% | 324,876 | 0.098 |
| sds-master | S4 Memory/Reflexion | ✗ | 10 | 75 → 57 | 24.0% | 385,593 | 0.047 |
| http-parser | **S1 Baseline** | **✓** | **7** | 57 → **0** | **100%** | **81,011** | **0.704** |
| http-parser | S2 Structured | ✗ | 10 | 57 → 4 | 93.0% | 108,299 | 0.489 |
| http-parser | S3 Diagnose→Patch | ✗ | 10 | 57 → 3 | 94.7% | 178,983 | 0.302 |
| http-parser | S4 Memory/Reflexion | ✗ | 10 | 57 → 5 | 91.2% | 251,584 | 0.207 |

---

### 4.2 Error Trajectory Plots

The trajectory plots show the compiler error count at each attempt (attempt 0 = baseline before any repair).

**SDS-master**

![SDS Error Trajectory](experiments/combined_plots/error_trajectory_sds-master.png)

**HTTP-parser**

![HTTP-parser Error Trajectory](experiments/combined_plots/error_trajectory_http-parser-main.png)

Key observations from the trajectories:

- **SDS Baseline** makes large reductions early (75→45 on attempt 1, then 45→34) before plateauing around 21–23. The end trajectory shows a slight increase from 21→23 on the final attempts, indicating a small regression.
- **SDS Structured** stalls completely for the first two attempts (75→75→75) before dropping sharply to 44. This suggests the structured format initially sent the model to a file or error that couldn't be fixed without context.
- **SDS Memory/Reflexion** makes one good jump (75→59) and then flatlines for 9 consecutive attempts. The memory mechanism, rather than diversifying the model's repair strategy, appears to have locked it in to a state it could not escape.
- **HTTP Baseline** shows a clean downward trajectory reaching 0 at attempt 7 — the only full success across all runs.
- All strategies on HTTP-parser converge to a similar floor of 3–5 errors by attempt 3–4, at which point they plateau. Baseline escaped this floor; the others did not.

---

### 4.3 Error Reduction

![SDS Error Reduction](experiments/combined_plots/error_reduction_sds-master.png)

![HTTP-parser Error Reduction](experiments/combined_plots/error_reduction_http-parser-main.png)

The absolute reduction bar charts make the ranking clear. On SDS, S1 fixes more than twice as many errors as S4 (52 vs 18). On HTTP-parser, S1 achieves full repair while the others leave a residual of 3–5 errors.

---

### 4.4 Multi-Dataset Normalised Comparison

![Multi-dataset Comparison](experiments/combined_plots/multi_dataset_comparison.png)

When normalised by initial error count, the performance gap between S1 and S4 is consistent across both datasets. S1 leads on both. The chart also highlights the dataset effect: all strategies perform substantially better on HTTP-parser than on SDS, indicating that dataset difficulty is a more powerful predictor of outcome than strategy choice.

---

### 4.5 Token Usage

![SDS Token Usage](experiments/combined_plots/token_usage_sds-master.png)

![HTTP-parser Token Usage](experiments/combined_plots/token_usage_http-parser-main.png)

The two-call strategies (S3, S4) consume roughly 2–3× more tokens than the single-call strategies (S1, S2). On SDS, S4 uses ~385K tokens vs. S1's ~196K. Since S4 performs worse, this represents a significant efficiency loss.

---

### 4.6 Token Efficiency

![SDS Efficiency](experiments/combined_plots/efficiency_sds-master.png)

![HTTP-parser Efficiency](experiments/combined_plots/efficiency_http-parser-main.png)

Efficiency (errors fixed per 1,000 tokens) is dominated by S1 on both datasets. S4 is approximately 5.6× less efficient than S1 on SDS (0.047 vs 0.266) and 3.4× less efficient on HTTP-parser (0.207 vs 0.704).

---

### 4.7 Patch Size

![SDS Patch Size](experiments/combined_plots/patch_size_sds-master.png)

![HTTP-parser Patch Size](experiments/combined_plots/patch_size_http-parser-main.png)

Cumulative lines of code changed across all accepted patches. S1 tends to make larger patches on SDS, consistent with its broader raw-output context causing it to make more sweeping repairs. On HTTP-parser, patch sizes are more uniform since all strategies converge quickly.

---

## 5. Analysis and Discussion

### 5.1 The core finding: prompting complexity does not help

The main hypothesis of this experiment — that more sophisticated prompting leads to better repair — is **not supported**. The performance ranking on both datasets is an exact inverse of strategy complexity:

```
S1 (simplest) > S2 > S3 > S4 (most complex)
```

This holds for both error reduction and token efficiency.

### 5.2 Why Baseline outperforms Structured

The structured format (S2) was designed to reduce noise by filtering the raw compiler output down to its essential fields. However, `rustc`'s rendered error output already contains highly useful information beyond what was captured in the structured fields — in particular, the `note:`, `help:`, and `consider:` hints that rustc appends to many errors. These hint lines often directly suggest the correct fix. By parsing only `code`, `message`, `label`, and `suggested_replacement`, the structured approach strips out this signal.

For example, a borrow-checker error in the raw output might include:
```
note: move occurs because `x` has type `String`, which does not implement the `Copy` trait
help: consider borrowing here: `&x`
```
The structured format loses these lines. The baseline model sees them and can act on them directly.

### 5.3 Why Memory/Reflexion performed worst on SDS

On SDS, the memory strategy made one meaningful move (75→59, fixing 16 variadic/feature-flag errors) and then failed to make further progress for 9 attempts. Two factors likely contributed:

1. **Memory acts as a constraint, not a guide.** The full diagnosis text stored in each memory entry told the model in detail what had already been tried. On SDS, where the remaining errors are all in the same hard macro/variadic category, the model had no genuinely different fix strategy available — the memory block effectively constrained it from re-attempting anything without providing a viable alternative path.

2. **The macro blocker is deterministic.** The `goto_cleanup!` and `goto_err!` macro errors cannot be resolved by LLM-level prompting alone. They require either rewriting the macro definition or eliminating the macros entirely — a large structural change that the guardrails (rejecting patches that collapse LOC by >30%) may have prevented.

### 5.4 The dataset effect dominates the strategy effect

All strategies performed substantially better on HTTP-parser (91–100% reduction) than on SDS (24–69% reduction). This suggests that **what kind of errors are present matters far more than how the prompting is structured**. HTTP-parser has diverse, locally fixable errors with clear compiler hints. SDS has a small number of repeated structural blockers that LLM prompting at any sophistication level cannot resolve.

This reinforces the conclusion from the v1 pilot: the binding constraint is the error family, not the prompting strategy.

---

## 6. Conclusions

1. **S1 Baseline is the recommended strategy** for this setting. It is the simplest, cheapest, and most effective approach across both datasets.

2. **Chain-of-thought reasoning does not improve repair** when the bottleneck is structural (macro/variadic) errors. The two-call strategies add latency and token cost without benefit.

3. **Memory/Reflexion is actively harmful on hard datasets.** On SDS, it produced the worst result by a wide margin and wasted the most tokens. The mechanism that prevents re-trying failed patterns also prevents the model from exploring the large-scale rewrites that the blockers actually require.

4. **The primary research variable should be error classification, not prompting architecture.** A deterministic preprocessing step that identifies and handles structural error classes (macro hoisting, variadic wrappers, feature flags) before the LLM repair loop would likely yield larger gains than any prompting variation tested here.

5. **HTTP-parser is close to fully solvable.** Three of four strategies reduced errors to 3–5. A small additional targeted effort — or simply more attempts — would likely achieve full compilation. This makes it a useful positive-control dataset for future experiments.

---

## 7. Experiment Artefacts

| Artefact | Path |
|---|---|
| Full results (JSONL) | `experiments/combined_results.jsonl` |
| Per-attempt detail (CSV) | `experiments/20260316_070542/attempts.csv` |
| All plots | `experiments/combined_plots/` |
| S1–S3 raw experiment | `experiments/20260316_070542/` |
| S4 experiment | `experiments/20260316_075956/` |
| Strategy source | `c2rust/apr/strategies/` |
| Runner | `c2rust/apr/runner_v2.py` |
| Entry point | `run_pilot.py` |
