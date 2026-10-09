import csv
import statistics
from pathlib import Path

try:
    import matplotlib.pyplot as plt
except ImportError:
    raise SystemExit(
        "缺少 matplotlib，请运行：python -m pip install matplotlib"
    )


ROOT = Path(__file__).resolve().parents[1]

RAW_FILE = ROOT / "experiments/raw/csv/sapling_output_prover_runs.csv"
SUMMARY_DIR = ROOT / "results/tables"
FIGURE_DIR = ROOT / "results/figures"

SUMMARY_FILE = SUMMARY_DIR / "sapling_output_prover_summary.csv"


def load_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"找不到原始数据文件：{path}")

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise ValueError("原始 CSV 中没有实验数据。")

    return rows


def calculate_stats(values):
    return {
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "stddev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def write_summary(summary):
    # 保留历史批次；重复运行脚本时更新同一批次，而不是重复添加。
    existing = []

    if SUMMARY_FILE.exists():
        with SUMMARY_FILE.open(
            "r", encoding="utf-8-sig", newline=""
        ) as f:
            existing = list(csv.DictReader(f))

    batch_id = str(summary["batch_id"])
    existing = [
        row for row in existing
        if row["batch_id"] != batch_id
    ]
    existing.append(summary)
    existing.sort(key=lambda row: int(row["batch_id"]))

    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)

    with SUMMARY_FILE.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary.keys()))
        writer.writeheader()
        writer.writerows(existing)


def plot_metric(runs, values, metric_name, ylabel, output_name):
    stats = calculate_stats(values)

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.plot(runs, values, marker="o", label=metric_name)
    ax.axhline(
        stats["median"],
        linestyle="--",
        label=f"Median = {stats['median']:.3f} ms",
    )

    ax.set_title(f"Sapling Output {metric_name} (latest batch)")
    ax.set_xlabel("Run")
    ax.set_ylabel(ylabel)
    ax.set_xticks(runs)
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()

    output_path = FIGURE_DIR / output_name
    fig.savefig(output_path, dpi=160)
    plt.close(fig)

    return output_path


def main():
    rows = load_csv(RAW_FILE)

    # 一次程序启动对应一个 batch，只绘制最新批次。
    latest_batch = max(int(row["batch_id"]) for row in rows)

    rows = [
        row for row in rows
        if int(row["batch_id"]) == latest_batch
    ]
    rows.sort(key=lambda row: int(row["run"]))

    runs = [int(row["run"]) for row in rows]
    prove_values = [float(row["prove_ms"]) for row in rows]
    verify_values = [float(row["verify_ms"]) for row in rows]
    proof_sizes = sorted({
        int(row["proof_bytes"]) for row in rows
    })

    prove = calculate_stats(prove_values)
    verify = calculate_stats(verify_values)

    summary = {
        "batch_id": str(latest_batch),
        "sample_count": len(rows),
        "params_read_validate_ms": rows[0]["params_read_validate_ms"],
        "prepare_vk_ms": rows[0]["prepare_vk_ms"],
        "input_prep_ms": rows[0]["input_prep_ms"],
        "prove_mean_ms": f"{prove['mean']:.3f}",
        "prove_median_ms": f"{prove['median']:.3f}",
        "prove_stddev_ms": f"{prove['stddev']:.3f}",
        "prove_min_ms": f"{prove['min']:.3f}",
        "prove_max_ms": f"{prove['max']:.3f}",
        "verify_mean_ms": f"{verify['mean']:.3f}",
        "verify_median_ms": f"{verify['median']:.3f}",
        "verify_stddev_ms": f"{verify['stddev']:.3f}",
        "verify_min_ms": f"{verify['min']:.3f}",
        "verify_max_ms": f"{verify['max']:.3f}",
        "proof_bytes": ";".join(map(str, proof_sizes)),
        "all_verified": all(
            row["verified"].strip().lower() == "true"
            for row in rows
        ),
        "rayon_threads": rows[0]["rayon_threads"],
    }

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    write_summary(summary)

    prove_plot = plot_metric(
        runs,
        prove_values,
        "Proving Time",
        "Proving time (ms)",
        "sapling_output_prove_ms.png",
    )

    verify_plot = plot_metric(
        runs,
        verify_values,
        "Verification Time",
        "Verification time (ms)",
        "sapling_output_verify_ms.png",
    )

    print(f"Latest batch: {latest_batch}")
    print(f"Sample count: {len(rows)}")
    print(f"All proofs verified: {summary['all_verified']}")
    print(f"Prove median: {prove['median']:.3f} ms")
    print(f"Verify median: {verify['median']:.3f} ms")
    print(f"Proof sizes: {proof_sizes} bytes")
    print(f"Summary: {SUMMARY_FILE}")
    print(f"Prove chart: {prove_plot}")
    print(f"Verify chart: {verify_plot}")


if __name__ == "__main__":
    main()