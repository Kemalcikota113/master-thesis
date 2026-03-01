"""Generate matplotlib plots from APR experiment CSV outputs."""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _to_int(value: str, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _to_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def plot_error_trajectory(attempt_rows: list[dict[str, str]], out_dir: Path):
    grouped: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for row in attempt_rows:
        strategy = row.get("strategy", "unknown")
        attempt = _to_int(row.get("attempt", "0"))
        errors_after = _to_int(row.get("errors_after", "0"))
        grouped[strategy].append((attempt, errors_after))

    plt.figure(figsize=(10, 6))
    for strategy, points in sorted(grouped.items()):
        points.sort(key=lambda item: item[0])
        x = [p[0] for p in points]
        y = [p[1] for p in points]
        plt.plot(x, y, marker="o", linewidth=2, label=strategy)

    plt.title("Compiler Errors vs APR Attempt")
    plt.xlabel("Attempt")
    plt.ylabel("Compiler Error Count")
    plt.xticks(sorted({p[0] for pts in grouped.values() for p in pts}))
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "error_trajectory.png", dpi=160)
    plt.close()


def plot_tokens(summary_rows: list[dict[str, str]], out_dir: Path):
    strategies = [row["strategy"] for row in summary_rows]
    tokens = [_to_int(row.get("tokens_total", "0")) for row in summary_rows]

    plt.figure(figsize=(10, 6))
    plt.bar(strategies, tokens)
    plt.title("Total Token Usage by Strategy")
    plt.xlabel("Strategy")
    plt.ylabel("Tokens")
    plt.xticks(rotation=15)
    plt.tight_layout()
    plt.savefig(out_dir / "token_usage.png", dpi=160)
    plt.close()


def plot_efficiency(summary_rows: list[dict[str, str]], out_dir: Path):
    strategies = [row["strategy"] for row in summary_rows]
    efficiency = []
    for row in summary_rows:
        reduction = _to_int(row.get("error_reduction", "0"))
        tokens = _to_float(row.get("tokens_total", "0"))
        value = (reduction / tokens * 1000.0) if tokens > 0 else 0.0
        efficiency.append(value)

    plt.figure(figsize=(10, 6))
    plt.bar(strategies, efficiency)
    plt.title("Repair Efficiency (Error Reduction per 1K Tokens)")
    plt.xlabel("Strategy")
    plt.ylabel("Errors Reduced / 1K Tokens")
    plt.xticks(rotation=15)
    plt.tight_layout()
    plt.savefig(out_dir / "efficiency_per_1k_tokens.png", dpi=160)
    plt.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create APR experiment plots from CSV outputs.",
        epilog="Example: python -m c2rust.plot_apr_results experiments/20260301_205213",
    )
    parser.add_argument("experiment_dir", help="Path to experiment folder")
    args = parser.parse_args()

    exp_dir = Path(args.experiment_dir).resolve()
    attempts_csv = exp_dir / "attempts.csv"
    summary_csv = exp_dir / "summary.csv"
    if not attempts_csv.exists() or not summary_csv.exists():
        print("Missing attempts.csv or summary.csv in experiment directory")
        return 1

    attempt_rows = _read_csv(attempts_csv)
    summary_rows = _read_csv(summary_csv)

    plots_dir = exp_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    plot_error_trajectory(attempt_rows, plots_dir)
    plot_tokens(summary_rows, plots_dir)
    plot_efficiency(summary_rows, plots_dir)

    print(f"Plots written to: {plots_dir}")
    print("- error_trajectory.png")
    print("- token_usage.png")
    print("- efficiency_per_1k_tokens.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
