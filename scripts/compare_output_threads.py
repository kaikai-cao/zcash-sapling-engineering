import csv
import statistics
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]

RAW = ROOT / "experiments/raw/csv/sapling_output_prover_runs_release.csv"
TABLE_DIR = ROOT / "results/tables"
FIGURE_DIR = ROOT / "results/figures"


def stats(values):
    return {
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "stddev": statistics.stdev(values) if len(values) > 1 else 0,
        "min": min(values),
        "max": max(values),
    }


def main():
    with RAW.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        if "build_profile" not in (reader.fieldnames or []):
            raise ValueError("CSV 缺少 build_profile 列，请先检查数据格式。")

        rows = [
            row for row in reader
            if row["build_profile"].strip().lower() == "release"
        ]

    if not rows:
        raise ValueError("没有找到 Release 实验数据。")

    groups = {}
    for row in rows:
        thread = row["rayon_threads"].strip()
        groups.setdefault(thread, []).append(row)

    threads = sorted(groups, key=int)
    summaries = []

    for thread in threads:
        items = groups[thread]
        prove = stats([float(r["prove_ms"]) for r in items])
        verify = stats([float(r["verify_ms"]) for r in items])
        sizes = sorted({int(r["proof_bytes"]) for r in items})

        summaries.append({
            "threads": thread,
            "samples": len(items),
            "prove_median_ms": f"{prove['median']:.3f}",
            "prove_mean_ms": f"{prove['mean']:.3f}",
            "prove_stddev_ms": f"{prove['stddev']:.3f}",
            "prove_min_ms": f"{prove['min']:.3f}",
            "prove_max_ms": f"{prove['max']:.3f}",
            "verify_median_ms": f"{verify['median']:.3f}",
            "verify_mean_ms": f"{verify['mean']:.3f}",
            "verify_stddev_ms": f"{verify['stddev']:.3f}",
            "proof_bytes": ";".join(map(str, sizes)),
            "all_verified": all(
                r["verified"].strip().lower() == "true"
                for r in items
            ),
        })

    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    summary_file = TABLE_DIR / "sapling_output_thread_comparison.csv"
    with summary_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=list(summaries[0].keys())
        )
        writer.writeheader()
        writer.writerows(summaries)

    # 比较两种指标：证明生成时间和验证时间。
    for metric, filename, ylabel in [
        ("prove_ms", "sapling_output_thread_prove.png",
         "Proving time (ms)"),
        ("verify_ms", "sapling_output_thread_verify.png",
         "Verification time (ms)"),
    ]:
        medians = [
            statistics.median(
                [float(r[metric]) for r in groups[t]]
            )
            for t in threads
        ]

        fig, ax = plt.subplots(figsize=(7, 5))
        positions = list(range(len(threads)))
        ax.bar(positions, medians, width=0.55, label="Median")

        for i, thread in enumerate(threads):
            values = [float(r[metric]) for r in groups[thread]]
            offsets = [
                (j - (len(values) - 1) / 2) * 0.045
                for j in range(len(values))
            ]
            ax.scatter(
                [i + x for x in offsets],
                values,
                marker="o",
                zorder=3,
                label="Individual runs" if i == 0 else None,
            )

        ax.set_xticks(positions, [f"{t} thread(s)" for t in threads])
        ax.set_ylabel(ylabel)
        ax.set_title(f"Sapling Output: {metric}")
        ax.grid(axis="y", alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(FIGURE_DIR / filename, dpi=160)
        plt.close(fig)

    print(f"Summary: {summary_file}")

    for filename in [
        "sapling_output_thread_prove.png",
        "sapling_output_thread_verify.png",
    ]:
        print(f"Chart: {FIGURE_DIR / filename}")

    if "1" in groups and "20" in groups:
        t1 = statistics.median(
            [float(r["prove_ms"]) for r in groups["1"]]
        )
        t20 = statistics.median(
            [float(r["prove_ms"]) for r in groups["20"]]
        )
        print(f"Proving speedup (20 threads): {t1 / t20:.2f}x")


if __name__ == "__main__":
    main()