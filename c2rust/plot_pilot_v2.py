"""Matplotlib plots for the APR v2 pilot experiment.

Generates the following plots in the given output directory:

  error_trajectory_<dataset>.png   — error count over attempts, one line per strategy
  token_usage_<dataset>.png        — prompt + completion tokens per strategy
  error_reduction_<dataset>.png    — absolute errors fixed per strategy
  efficiency_<dataset>.png         — error reduction per 1K tokens
  patch_size_<dataset>.png         — cumulative LOC changed per strategy
  multi_dataset_comparison.png     — normalised error reduction across datasets (≥2)

Call `generate_plots(results_jsonl, attempts_csv, plots_dir)` from run_pilot.py.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # headless — no display required
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker


# ---------------------------------------------------------------------------
# Consistent colour palette and display labels
# ---------------------------------------------------------------------------

_COLOURS: dict[str, str] = {
    "baseline":            "#4e79a7",
    "structured_compiler": "#f28e2b",
    "diagnose_then_patch": "#59a14f",
    "memory_reflexion":    "#e15759",
}

_LABELS: dict[str, str] = {
    "baseline":            "S1 Baseline",
    "structured_compiler": "S2 Structured",
    "diagnose_then_patch": "S3 Diagnose→Patch",
    "memory_reflexion":    "S4 Memory/Reflexion",
}

# Canonical iteration order for all bar charts.
AprStrategyV2Order: list[str] = [
    "baseline",
    "structured_compiler",
    "diagnose_then_patch",
    "memory_reflexion",
]


def _colour(strategy: str) -> str:
    return _COLOURS.get(strategy, "#888888")


def _label(strategy: str) -> str:
    return _LABELS.get(strategy, strategy)


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _load_results(results_jsonl: Path) -> list[dict]:
    records = []
    with results_jsonl.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _load_attempts(attempts_csv: Path) -> list[dict]:
    if not attempts_csv.exists():
        return []
    with attempts_csv.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------

def _bar_axes(ax: plt.Axes, labels: list[str]) -> None:
    """Set integer x-ticks with rotated string labels for bar charts."""
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=15, ha="right", fontsize=9)


# ---------------------------------------------------------------------------
# Plot 1: Error trajectory (line chart)
# ---------------------------------------------------------------------------

def _plot_error_trajectory(records: list[dict], plots_dir: Path) -> None:
    datasets = sorted({r["dataset_name"] for r in records if r.get("error_reduction_trajectory")})
    for ds in datasets:
        ds_records = [
            r for r in records
            if r["dataset_name"] == ds and r.get("error_reduction_trajectory")
        ]
        if not ds_records:
            continue

        fig, ax = plt.subplots(figsize=(9, 5))
        for r in ds_records:
            traj = r["error_reduction_trajectory"]
            strategy = r["strategy_name"]
            ax.plot(
                range(len(traj)), traj,
                marker="o", linewidth=2, markersize=5,
                color=_colour(strategy), label=_label(strategy),
            )
            if r["compile_success"] and traj[-1] == 0:
                ax.annotate(
                    "✓", (len(traj) - 1, 0),
                    textcoords="offset points", xytext=(4, 4),
                    color=_colour(strategy), fontsize=11,
                )

        ax.set_title(f"Compiler Errors vs APR Attempt — {ds}", fontsize=13)
        ax.set_xlabel("Attempt", fontsize=11)
        ax.set_ylabel("Compiler Error Count", fontsize=11)
        ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
        ax.legend(loc="upper right", fontsize=9)
        ax.grid(axis="y", linestyle="--", alpha=0.5)
        fig.tight_layout()
        fig.savefig(plots_dir / f"error_trajectory_{ds.replace('/', '__')}.png", dpi=150)
        plt.close(fig)


# ---------------------------------------------------------------------------
# Plot 2: Token usage (grouped bar)
# ---------------------------------------------------------------------------

def _plot_token_usage(records: list[dict], plots_dir: Path) -> None:
    datasets = sorted({r["dataset_name"] for r in records})
    for ds in datasets:
        ds_map = {r["strategy_name"]: r for r in records if r["dataset_name"] == ds}
        ordered = [s for s in AprStrategyV2Order if s in ds_map]
        if not ordered:
            continue

        labels = [_label(s) for s in ordered]
        prompt_vals = [ds_map[s]["total_prompt_tokens"] for s in ordered]
        completion_vals = [ds_map[s]["total_completion_tokens"] for s in ordered]
        x = range(len(ordered))
        width = 0.35

        fig, ax = plt.subplots(figsize=(9, 5))
        ax.bar([i - width / 2 for i in x], prompt_vals, width,
               label="Prompt tokens", color="#aec7e8")
        ax.bar([i + width / 2 for i in x], completion_vals, width,
               label="Completion tokens", color="#ffbb78")

        ax.set_title(f"Token Usage per Strategy — {ds}", fontsize=13)
        ax.set_ylabel("Tokens", fontsize=11)
        _bar_axes(ax, labels)
        ax.legend(fontsize=9)
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
        ax.grid(axis="y", linestyle="--", alpha=0.5)
        fig.tight_layout()
        fig.savefig(plots_dir / f"token_usage_{ds.replace('/', '__')}.png", dpi=150)
        plt.close(fig)


# ---------------------------------------------------------------------------
# Plot 3: Error reduction (bar)
# ---------------------------------------------------------------------------

def _plot_error_reduction(records: list[dict], plots_dir: Path) -> None:
    datasets = sorted({r["dataset_name"] for r in records})
    for ds in datasets:
        ds_map = {r["strategy_name"]: r for r in records if r["dataset_name"] == ds}
        ordered = [s for s in AprStrategyV2Order if s in ds_map]
        if not ordered:
            continue

        labels = [_label(s) for s in ordered]
        reductions = [
            ds_map[s]["initial_error_count"] - ds_map[s]["final_error_count"]
            for s in ordered
        ]
        colours = [_colour(s) for s in ordered]

        fig, ax = plt.subplots(figsize=(8, 5))
        bars = ax.bar(range(len(ordered)), reductions, color=colours,
                      edgecolor="white", linewidth=0.8)
        for bar, val in zip(bars, reductions):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.3,
                str(val), ha="center", va="bottom", fontsize=10,
            )
        ax.set_title(f"Total Error Reduction per Strategy — {ds}", fontsize=13)
        ax.set_ylabel("Errors Fixed (initial − final)", fontsize=11)
        _bar_axes(ax, labels)
        ax.grid(axis="y", linestyle="--", alpha=0.5)
        fig.tight_layout()
        fig.savefig(plots_dir / f"error_reduction_{ds.replace('/', '__')}.png", dpi=150)
        plt.close(fig)


# ---------------------------------------------------------------------------
# Plot 4: Efficiency (error reduction per 1K tokens)
# ---------------------------------------------------------------------------

def _plot_efficiency(records: list[dict], plots_dir: Path) -> None:
    datasets = sorted({r["dataset_name"] for r in records})
    for ds in datasets:
        ds_map = {r["strategy_name"]: r for r in records if r["dataset_name"] == ds}
        ordered = [s for s in AprStrategyV2Order if s in ds_map]
        if not ordered:
            continue

        labels, efficiencies, colours = [], [], []
        for s in ordered:
            r = ds_map[s]
            total_tokens = r["total_prompt_tokens"] + r["total_completion_tokens"]
            reduction = r["initial_error_count"] - r["final_error_count"]
            eff = (reduction / total_tokens * 1000) if total_tokens > 0 else 0.0
            labels.append(_label(s))
            efficiencies.append(round(eff, 3))
            colours.append(_colour(s))

        fig, ax = plt.subplots(figsize=(8, 5))
        bars = ax.bar(range(len(ordered)), efficiencies, color=colours,
                      edgecolor="white", linewidth=0.8)
        for bar, val in zip(bars, efficiencies):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.001,
                f"{val:.3f}", ha="center", va="bottom", fontsize=10,
            )
        ax.set_title(f"Efficiency: Error Reduction per 1K Tokens — {ds}", fontsize=13)
        ax.set_ylabel("Errors fixed per 1K tokens", fontsize=11)
        _bar_axes(ax, labels)
        ax.grid(axis="y", linestyle="--", alpha=0.5)
        fig.tight_layout()
        fig.savefig(plots_dir / f"efficiency_{ds.replace('/', '__')}.png", dpi=150)
        plt.close(fig)


# ---------------------------------------------------------------------------
# Plot 5: Patch size (cumulative LOC changed)
# ---------------------------------------------------------------------------

def _plot_patch_size(records: list[dict], plots_dir: Path) -> None:
    datasets = sorted({r["dataset_name"] for r in records})
    for ds in datasets:
        ds_map = {r["strategy_name"]: r for r in records if r["dataset_name"] == ds}
        ordered = [s for s in AprStrategyV2Order if s in ds_map]
        if not ordered:
            continue

        labels = [_label(s) for s in ordered]
        sizes = [ds_map[s]["patch_size_loc"] for s in ordered]
        colours = [_colour(s) for s in ordered]

        fig, ax = plt.subplots(figsize=(8, 5))
        bars = ax.bar(range(len(ordered)), sizes, color=colours,
                      edgecolor="white", linewidth=0.8)
        for bar, val in zip(bars, sizes):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.5,
                str(val), ha="center", va="bottom", fontsize=10,
            )
        ax.set_title(f"Cumulative Patch Size (LOC Changed) — {ds}", fontsize=13)
        ax.set_ylabel("Lines of code changed", fontsize=11)
        _bar_axes(ax, labels)
        ax.grid(axis="y", linestyle="--", alpha=0.5)
        fig.tight_layout()
        fig.savefig(plots_dir / f"patch_size_{ds.replace('/', '__')}.png", dpi=150)
        plt.close(fig)


# ---------------------------------------------------------------------------
# Plot 6: Multi-dataset normalised comparison
# ---------------------------------------------------------------------------

def _plot_multi_dataset_comparison(records: list[dict], plots_dir: Path) -> None:
    """Normalised error reduction (% of initial errors fixed) across all datasets."""
    datasets = sorted({r["dataset_name"] for r in records})
    if len(datasets) < 2:
        return

    norm_reductions: dict[str, list[float]] = defaultdict(list)
    for ds in datasets:
        ds_map = {r["strategy_name"]: r for r in records if r["dataset_name"] == ds}
        for s in AprStrategyV2Order:
            r = ds_map.get(s)
            if r and r["initial_error_count"] > 0:
                norm = (r["initial_error_count"] - r["final_error_count"]) / r["initial_error_count"]
            else:
                norm = 0.0
            norm_reductions[s].append(norm)

    active = [s for s in AprStrategyV2Order if norm_reductions[s]]
    n_ds = len(datasets)
    n_s = len(active)
    width = 0.8 / n_s
    offsets = [(i - (n_s - 1) / 2) * width for i in range(n_s)]

    fig, ax = plt.subplots(figsize=(10, 5))
    x = range(n_ds)
    for offset, s in zip(offsets, active):
        ax.bar(
            [xi + offset for xi in x],
            [v * 100 for v in norm_reductions[s]],
            width=width * 0.9,
            label=_label(s), color=_colour(s), edgecolor="white",
        )

    ax.set_title("Normalised Error Reduction (%) Across Datasets", fontsize=13)
    ax.set_ylabel("% of initial errors fixed", fontsize=11)
    ax.set_xticks(list(x))
    ax.set_xticklabels(datasets, rotation=15, ha="right", fontsize=9)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    fig.tight_layout()
    fig.savefig(plots_dir / "multi_dataset_comparison.png", dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_plots(
    results_jsonl: Path,
    attempts_csv: Path,
    plots_dir: Path,
) -> None:
    """Generate all plots from experiment output files."""
    if not results_jsonl.exists():
        print(f"  [plots] results.jsonl not found at {results_jsonl}")
        return

    plots_dir.mkdir(parents=True, exist_ok=True)
    records = _load_results(results_jsonl)
    valid = [r for r in records if r.get("error_reduction_trajectory")]

    if not valid:
        print("  [plots] No valid results with trajectory data to plot.")
        return

    print(f"  Generating plots for {len(valid)} run(s) → {plots_dir}")
    _plot_error_trajectory(valid, plots_dir)
    _plot_token_usage(valid, plots_dir)
    _plot_error_reduction(valid, plots_dir)
    _plot_efficiency(valid, plots_dir)
    _plot_patch_size(valid, plots_dir)
    _plot_multi_dataset_comparison(valid, plots_dir)
    print(f"  Done. {len(list(plots_dir.glob('*.png')))} plots saved.")
