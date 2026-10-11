import csv
import statistics
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]

RAW = ROOT / "experiments/raw/csv/sapling_output_prover_runs_release.csv"
TABLE_DIR = ROOT / "results/tables"
FIGURE_DIR = ROOT / "results/figures"

# 固定实验批次，防止历史数据混入。
SELECTED_BATCHES = {
    "1791527316042": "1",
    "1791527583309": "20",
}

THREAD_BATCHES = {threads: batch_id for batch_id, threads in SELECTED_BATCHES.items()}


def stats(values):
    return {
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "stddev": statistics.stdev(values) if len(values) > 1 else 0,
        "min": min(values),
        "max": max(values),
    }


def main():
    # 1. 读取原始数据，只选择指定批次。
    with RAW.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        required_columns = {
            "batch_id",
            "run",
            "rayon_threads",
            "build_profile",
            "prove_ms",
            "verify_ms",
            "proof_bytes",
            "verified",
        }

        available = set(reader.fieldnames or [])
        missing = required_columns - available

        if missing:
            raise ValueError(f"CSV 缺少字段：{', '.join(sorted(missing))}")

        rows = [row for row in reader if row["batch_id"].strip() in SELECTED_BATCHES]

    if not rows:
        raise ValueError("没有找到指定的线程对比实验批次。")

    # 2. 检查每个批次的数据是否完整、有效。
    for batch_id, expected_threads in SELECTED_BATCHES.items():
        batch_rows = [row for row in rows if row["batch_id"].strip() == batch_id]

        if len(batch_rows) != 5:
            raise ValueError(
                f"批次 {batch_id} 应有 5 次测量，" f"实际找到 {len(batch_rows)} 次。"
            )

        run_ids = [row["run"].strip() for row in batch_rows]
        if len(set(run_ids)) != 5 or set(run_ids) != {"1", "2", "3", "4", "5"}:
            raise ValueError(f"批次 {batch_id} 的 run 编号重复或不完整。")

        if any(row["rayon_threads"].strip() != expected_threads for row in batch_rows):
            raise ValueError(f"批次 {batch_id} 的线程配置与预期不符。")

        if any(row["build_profile"].strip().lower() != "release" for row in batch_rows):
            raise ValueError(f"批次 {batch_id} 并非全部使用 Release 配置。")

        if any(row["verified"].strip().lower() != "true" for row in batch_rows):
            raise ValueError(f"批次 {batch_id} 存在验证失败的证明。")

        print(
            f"[CHECK PASS] batch={batch_id}, "
            f"threads={expected_threads}, samples=5, verified=5/5"
        )

    # 3. 按线程数分组。
    groups = {}
    for row in rows:
        thread = row["rayon_threads"].strip()
        groups.setdefault(thread, []).append(row)

    threads = sorted(groups, key=int)
    summaries = []

    # 4. 生成统计表。
    for thread in threads:
        items = groups[thread]
        prove = stats([float(r["prove_ms"]) for r in items])
        verify = stats([float(r["verify_ms"]) for r in items])
        sizes = sorted({int(r["proof_bytes"]) for r in items})

        summaries.append(
            {
                "batch_id": THREAD_BATCHES[thread],
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
                    r["verified"].strip().lower() == "true" for r in items
                ),
            }
        )

    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    summary_file = TABLE_DIR / "sapling_output_thread_comparison.csv"

    with summary_file.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summaries[0].keys()))
        writer.writeheader()
        writer.writerows(summaries)

    # 5. 生成 Prove / Verify 对比图。
    for metric, filename, ylabel in [
        ("prove_ms", "sapling_output_thread_prove.png", "Proving time (ms)"),
        ("verify_ms", "sapling_output_thread_verify.png", "Verification time (ms)"),
    ]:
        medians = [
            statistics.median([float(r[metric]) for r in groups[t]]) for t in threads
        ]

        fig, ax = plt.subplots(figsize=(7, 5))
        positions = list(range(len(threads)))
        ax.bar(positions, medians, width=0.55, label="Median")

        for i, thread in enumerate(threads):
            values = [float(r[metric]) for r in groups[thread]]
            offsets = [(j - (len(values) - 1) / 2) * 0.045 for j in range(len(values))]
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

    # 6. 输出结果摘要。
    print(f"\nSummary: {summary_file}")

    for filename in [
        "sapling_output_thread_prove.png",
        "sapling_output_thread_verify.png",
    ]:
        print(f"Chart: {FIGURE_DIR / filename}")

    t1 = statistics.median([float(r["prove_ms"]) for r in groups["1"]])
    t20 = statistics.median([float(r["prove_ms"]) for r in groups["20"]])

    print(f"\n1-thread Prove median: {t1:.3f} ms")
    print(f"20-thread Prove median: {t20:.3f} ms")
    print(f"Observed speedup: {t1 / t20:.2f}x")


if __name__ == "__main__":
    main()
