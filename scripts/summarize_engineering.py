import csv
from collections import defaultdict
from pathlib import Path
from statistics import median

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ============================================================
# 0. 路径和基准配置
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "experiments" / "raw" / "csv"
TABLE_DIR = ROOT / "results" / "tables"
FIGURE_DIR = ROOT / "results" / "figures"

SOURCE_VERSION = "0.9.0"
SOURCE_COMMIT = "88a7946b4a3066787776e11f0a502654167e022d"

SCALE_RAW = RAW_DIR / "sapling_circuit_scale_raw.csv"
PARAMS_RAW = RAW_DIR / "sapling_parameter_metadata_raw.csv"

PERFORMANCE_RAW = {
    "Spend": RAW_DIR / "sapling_spend_prover_runs_release.csv",
    "Output": RAW_DIR / "sapling_output_prover_runs_release.csv",
}

# 只纳入我们选定的、恢复官方实现后的正式基准批次。
# 原始 CSV 不删除、不修改；其他历史批次仍然完整保留。
BASELINE_BATCH_IDS = {
    "Spend": {"1791613854129"},
    "Output": {"1791549582046"},
}

SCALE_OUT = TABLE_DIR / "engineering_scale.csv"
PARAMS_OUT = TABLE_DIR / "engineering_parameters.csv"
PERFORMANCE_OUT = TABLE_DIR / "engineering_performance.csv"


# ============================================================
# 1. 通用 CSV 工具
# ============================================================


def read_csv(path):
    if not path.is_file():
        raise FileNotFoundError(f"找不到原始数据文件：{path}")

    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        raise ValueError(f"CSV 没有数据记录：{path}")

    return rows


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="raise",
        )
        writer.writeheader()
        writer.writerows(rows)


def require_columns(rows, required, path):
    if not rows:
        raise ValueError(f"没有可供检查的数据：{path}")

    available = set(rows[0].keys())
    missing = set(required) - available

    if missing:
        raise ValueError(f"{path.name} 缺少字段：{', '.join(sorted(missing))}")


def parse_bool(value, context):
    text = str(value).strip().lower()

    if text == "true":
        return True

    if text == "false":
        return False

    raise ValueError(f"{context} 中出现非法布尔值：{value!r}")


# ============================================================
# 2. 电路规模汇总
# ============================================================


def summarize_scale():
    rows = read_csv(SCALE_RAW)

    require_columns(
        rows,
        [
            "circuit",
            "constraints",
            "auxiliary_variables",
            "public_inputs_excluding_one",
            "input_variables_including_one",
            "domain_size_estimate",
        ],
        SCALE_RAW,
    )

    fields = [
        "circuit",
        "source_version",
        "source_commit",
        "constraints",
        "auxiliary_variables",
        "public_inputs_excluding_one",
        "input_variables_including_one",
        "domain_size_estimate",
        "domain_size_method",
        "measurement_method",
    ]

    output_rows = []

    for row in rows:
        constraints = int(row["constraints"])
        domain_size = int(row["domain_size_estimate"])

        if constraints <= 0:
            raise ValueError(f"{row['circuit']} 的约束数必须大于 0")

        # 域大小是根据约束数计算的估计值，而非实测值。
        expected_domain = 1 << (constraints - 1).bit_length()

        if domain_size != expected_domain:
            raise ValueError(
                f"{row['circuit']} 域大小不一致："
                f"记录值={domain_size}，预期值={expected_domain}"
            )

        output_rows.append(
            {
                "circuit": row["circuit"],
                "source_version": SOURCE_VERSION,
                "source_commit": SOURCE_COMMIT,
                "constraints": constraints,
                "auxiliary_variables": int(row["auxiliary_variables"]),
                "public_inputs_excluding_one": int(row["public_inputs_excluding_one"]),
                "input_variables_including_one": int(
                    row["input_variables_including_one"]
                ),
                "domain_size_estimate": domain_size,
                "domain_size_method": "next_power_of_two(constraints)",
                "measurement_method": (
                    "Counting ConstraintSystem; "
                    "domain size is estimated, not directly measured"
                ),
            }
        )

    write_csv(SCALE_OUT, fields, output_rows)
    print(f"[OK] 电路规模表：{SCALE_OUT}")

    return output_rows


# ============================================================
# 3. 参数文件汇总
# ============================================================


def summarize_parameters():
    rows = read_csv(PARAMS_RAW)

    require_columns(
        rows,
        [
            "batch_id",
            "parameter",
            "circuit",
            "source_version",
            "source_commit",
            "path",
            "file_bytes",
            "sha256",
            "blake2b512",
            "load_validate_ms",
            "point_encodings_verified",
        ],
        PARAMS_RAW,
    )

    groups = defaultdict(list)

    for row in rows:
        groups[row["parameter"]].append(row)

    fields = [
        "parameter",
        "circuit",
        "source_version",
        "source_commit",
        "path",
        "file_bytes",
        "file_mib",
        "sha256",
        "blake2b512",
        "point_encodings_verified",
        "measurement_count",
        "load_validate_median_ms",
        "load_validate_min_ms",
        "load_validate_max_ms",
    ]

    output_rows = []

    stable_fields = [
        "circuit",
        "source_version",
        "source_commit",
        "path",
        "file_bytes",
        "sha256",
        "blake2b512",
        "point_encodings_verified",
    ]

    for parameter, group_rows in groups.items():
        for field in stable_fields:
            values = {row[field] for row in group_rows}

            if len(values) != 1:
                raise ValueError(f"{parameter} 的 {field} " "在不同批次中不一致")

        if not parse_bool(
            group_rows[0]["point_encodings_verified"],
            f"{parameter}.point_encodings_verified",
        ):
            raise ValueError(f"{parameter} 没有通过点编码验证")

        batch_ids = [row["batch_id"] for row in group_rows]

        if len(batch_ids) != len(set(batch_ids)):
            raise ValueError(f"{parameter} 存在重复 batch_id，" "请检查原始参数 CSV")

        times = [float(row["load_validate_ms"]) for row in group_rows]

        if any(t < 0 for t in times):
            raise ValueError(f"{parameter} 出现负耗时")

        file_bytes = int(group_rows[0]["file_bytes"])

        output_rows.append(
            {
                "parameter": parameter,
                "circuit": group_rows[0]["circuit"],
                "source_version": group_rows[0]["source_version"],
                "source_commit": group_rows[0]["source_commit"],
                "path": group_rows[0]["path"],
                "file_bytes": file_bytes,
                "file_mib": f"{file_bytes / (1024 * 1024):.3f}",
                "sha256": group_rows[0]["sha256"],
                "blake2b512": group_rows[0]["blake2b512"],
                "point_encodings_verified": "true",
                "measurement_count": len(times),
                "load_validate_median_ms": f"{median(times):.3f}",
                "load_validate_min_ms": f"{min(times):.3f}",
                "load_validate_max_ms": f"{max(times):.3f}",
            }
        )

    circuit_order = {"Spend": 0, "Output": 1}
    output_rows.sort(key=lambda row: circuit_order.get(row["circuit"], 99))

    write_csv(PARAMS_OUT, fields, output_rows)
    print(f"[OK] 参数信息表：{PARAMS_OUT}")

    return output_rows


# ============================================================
# 4. 正式基准性能汇总
# ============================================================


def summarize_performance():
    required_fields = [
        "batch_id",
        "run",
        "params_read_validate_ms",
        "prepare_vk_ms",
        "input_prep_ms",
        "prove_ms",
        "verify_ms",
        "proof_bytes",
        "verified",
        "rayon_threads",
        "build_profile",
    ]

    # 先读取并筛选指定的正式基准批次。
    selected_records = []

    for circuit, path in PERFORMANCE_RAW.items():
        raw_rows = read_csv(path)
        require_columns(raw_rows, required_fields, path)

        selected_ids = BASELINE_BATCH_IDS[circuit]

        circuit_rows = [
            row for row in raw_rows if row["batch_id"].strip() in selected_ids
        ]

        found_ids = {row["batch_id"].strip() for row in circuit_rows}
        missing_ids = selected_ids - found_ids

        if missing_ids:
            raise ValueError(
                f"{circuit} 缺少指定的正式基准批次："
                f"{sorted(missing_ids)}；"
                f"请检查 {path.name} 中的 batch_id"
            )

        for row in circuit_rows:
            record = dict(row)
            record["circuit"] = circuit
            record["verified_bool"] = parse_bool(
                row["verified"],
                f"{path.name}, batch_id={row['batch_id']}, " f"run={row['run']}",
            )

            selected_records.append(record)

    # 防止重复记录被计入统计量。
    seen_runs = set()

    for row in selected_records:
        identity = (
            row["circuit"],
            row["batch_id"],
            row["run"],
        )

        if identity in seen_runs:
            raise ValueError(f"检测到重复实验记录：{identity}")

        seen_runs.add(identity)

    # 按电路、线程数和构建模式分组，禁止混合配置。
    groups = defaultdict(list)

    for row in selected_records:
        key = (
            row["circuit"],
            row["rayon_threads"].strip(),
            row["build_profile"].strip(),
        )

        groups[key].append(row)

    fields = [
        "circuit",
        "rayon_threads",
        "build_profile",
        "batch_count",
        "batch_ids",
        "measurement_count",
        "verified_count",
        "failed_count",
        "all_verified",
        "proof_bytes",
        "params_read_validate_median_ms",
        "prepare_vk_median_ms",
        "input_prep_median_ms",
        "prove_median_ms",
        "prove_min_ms",
        "prove_max_ms",
        "verify_median_ms",
        "verify_min_ms",
        "verify_max_ms",
    ]

    output_rows = []

    for (circuit, threads, profile), group_rows in groups.items():
        batch_ids = sorted({row["batch_id"].strip() for row in group_rows})

        proof_sizes = {int(row["proof_bytes"]) for row in group_rows}

        if len(proof_sizes) != 1:
            raise ValueError(f"{circuit} 的证明大小不一致：" f"{sorted(proof_sizes)}")

        verified_count = sum(1 for row in group_rows if row["verified_bool"])
        failed_count = len(group_rows) - verified_count

        def times(field):
            result = [float(row[field]) for row in group_rows]

            if any(value < 0 for value in result):
                raise ValueError(f"{circuit}.{field} 出现负耗时")

            return result

        prove_times = times("prove_ms")
        verify_times = times("verify_ms")
        params_times = times("params_read_validate_ms")
        vk_times = times("prepare_vk_ms")
        input_times = times("input_prep_ms")

        output_rows.append(
            {
                "circuit": circuit,
                "rayon_threads": threads,
                "build_profile": profile,
                "batch_count": len(batch_ids),
                "batch_ids": ";".join(batch_ids),
                "measurement_count": len(group_rows),
                "verified_count": verified_count,
                "failed_count": failed_count,
                "all_verified": ("true" if failed_count == 0 else "false"),
                "proof_bytes": next(iter(proof_sizes)),
                "params_read_validate_median_ms": (f"{median(params_times):.3f}"),
                "prepare_vk_median_ms": f"{median(vk_times):.3f}",
                "input_prep_median_ms": f"{median(input_times):.3f}",
                "prove_median_ms": f"{median(prove_times):.3f}",
                "prove_min_ms": f"{min(prove_times):.3f}",
                "prove_max_ms": f"{max(prove_times):.3f}",
                "verify_median_ms": f"{median(verify_times):.3f}",
                "verify_min_ms": f"{min(verify_times):.3f}",
                "verify_max_ms": f"{max(verify_times):.3f}",
            }
        )

    circuit_order = {"Spend": 0, "Output": 1}
    output_rows.sort(
        key=lambda row: (
            circuit_order.get(row["circuit"], 99),
            row["rayon_threads"],
            row["build_profile"],
        )
    )

    write_csv(PERFORMANCE_OUT, fields, output_rows)
    print(f"[OK] 证明性能表：{PERFORMANCE_OUT}")

    for row in output_rows:
        print(
            f"  {row['circuit']}: "
            f"batch={row['batch_ids']}, "
            f"prove median={row['prove_median_ms']} ms, "
            f"verify median={row['verify_median_ms']} ms, "
            f"proof={row['proof_bytes']} bytes, "
            f"verified={row['verified_count']}/"
            f"{row['measurement_count']}, "
            f"threads={row['rayon_threads']}, "
            f"profile={row['build_profile']}"
        )

    return output_rows


# ============================================================
# 5. 通用柱状图
# ============================================================


def save_bar_chart(
    labels,
    values,
    title,
    ylabel,
    output_path,
    formatter=str,
):
    fig, ax = plt.subplots(figsize=(8, 5))

    bars = ax.bar(labels, values)

    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.set_axisbelow(True)

    for bar, value in zip(bars, values):
        ax.annotate(
            formatter(value),
            (
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
            ),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
        )

    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)

    print(f"[OK] 图表：{output_path}")


# ============================================================
# 6. 原有四张图：规模和参数
# ============================================================


def generate_scale_and_parameter_figures(
    scale_rows,
    parameter_rows,
):
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    save_bar_chart(
        [row["circuit"] for row in scale_rows],
        [int(row["constraints"]) for row in scale_rows],
        "Sapling Circuit Constraints",
        "Number of Constraints",
        FIGURE_DIR / "sapling_circuit_constraints.png",
        formatter=lambda value: f"{value:,}",
    )

    save_bar_chart(
        [row["circuit"] for row in scale_rows],
        [int(row["auxiliary_variables"]) for row in scale_rows],
        "Sapling Circuit Auxiliary Variables",
        "Number of Auxiliary Variables",
        FIGURE_DIR / "sapling_circuit_auxiliary_variables.png",
        formatter=lambda value: f"{value:,}",
    )

    save_bar_chart(
        [row["circuit"] for row in parameter_rows],
        [int(row["file_bytes"]) / (1024 * 1024) for row in parameter_rows],
        "Sapling Parameter File Sizes",
        "File Size (MiB)",
        FIGURE_DIR / "sapling_parameter_sizes.png",
        formatter=lambda value: f"{value:.3f}",
    )

    title = "Parameter Load and Point-Encoding Validation Time"

    if all(int(row["measurement_count"]) == 1 for row in parameter_rows):
        title += "\n(single measurement per parameter)"

    save_bar_chart(
        [row["circuit"] for row in parameter_rows],
        [float(row["load_validate_median_ms"]) / 1000 for row in parameter_rows],
        title,
        "Time (seconds)",
        FIGURE_DIR / "sapling_parameter_load_validate.png",
        formatter=lambda value: f"{value:.2f} s",
    )


# ============================================================
# 7. 证明性能图：只画全部验证通过的正式配置
# ============================================================


def generate_performance_figures(performance_rows):
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    # 使用数值计数判断，不依赖 all_verified 字符串的格式。
    valid_rows = [
        row
        for row in performance_rows
        if int(row["measurement_count"]) > 0
        and int(row["failed_count"]) == 0
        and int(row["verified_count"]) == int(row["measurement_count"])
    ]

    if not valid_rows:
        raise ValueError(
            "正式基准批次中没有所有证明均验证成功的配置。"
            "请检查 engineering_performance.csv 和原始 CSV。"
        )

    labels = [
        f"{row['circuit']}\n" f"threads={row['rayon_threads']}, {row['build_profile']}"
        for row in valid_rows
    ]

    # 图 5：证明生成耗时。
    # 误差线仅表示本批次最小值和最大值，不是置信区间。
    prove_medians = [float(row["prove_median_ms"]) / 1000 for row in valid_rows]

    prove_lower = [
        max(
            0.0,
            (float(row["prove_median_ms"]) - float(row["prove_min_ms"])) / 1000,
        )
        for row in valid_rows
    ]

    prove_upper = [
        max(
            0.0,
            (float(row["prove_max_ms"]) - float(row["prove_median_ms"])) / 1000,
        )
        for row in valid_rows
    ]

    fig, ax = plt.subplots(figsize=(9, 5))

    bars = ax.bar(
        range(len(valid_rows)),
        prove_medians,
        yerr=[prove_lower, prove_upper],
        capsize=4,
    )

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels)
    ax.set_title("Sapling Proof Generation Time")
    ax.set_ylabel("Proving Time (seconds)")
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.set_axisbelow(True)

    for bar, row in zip(bars, valid_rows):
        ax.annotate(
            f"{float(row['prove_median_ms']) / 1000:.2f} s",
            (
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
            ),
            xytext=(0, 6),
            textcoords="offset points",
            ha="center",
            va="bottom",
        )

    fig.tight_layout()
    fig.savefig(
        FIGURE_DIR / "sapling_prove_time.png",
        dpi=160,
        bbox_inches="tight",
    )
    plt.close(fig)

    print("[OK] 图表：" f"{FIGURE_DIR / 'sapling_prove_time.png'}")

    # 图 6：验证耗时。
    verify_medians = [float(row["verify_median_ms"]) for row in valid_rows]

    verify_lower = [
        max(
            0.0,
            float(row["verify_median_ms"]) - float(row["verify_min_ms"]),
        )
        for row in valid_rows
    ]

    verify_upper = [
        max(
            0.0,
            float(row["verify_max_ms"]) - float(row["verify_median_ms"]),
        )
        for row in valid_rows
    ]

    fig, ax = plt.subplots(figsize=(9, 5))

    bars = ax.bar(
        range(len(valid_rows)),
        verify_medians,
        yerr=[verify_lower, verify_upper],
        capsize=4,
    )

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels)
    ax.set_title("Sapling Proof Verification Time")
    ax.set_ylabel("Verification Time (ms)")
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.set_axisbelow(True)

    for bar, row in zip(bars, valid_rows):
        ax.annotate(
            f"{float(row['verify_median_ms']):.2f} ms",
            (
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
            ),
            xytext=(0, 6),
            textcoords="offset points",
            ha="center",
            va="bottom",
        )

    fig.tight_layout()
    fig.savefig(
        FIGURE_DIR / "sapling_verify_time.png",
        dpi=160,
        bbox_inches="tight",
    )
    plt.close(fig)

    print("[OK] 图表：" f"{FIGURE_DIR / 'sapling_verify_time.png'}")

    # 图 7：证明大小。
    save_bar_chart(
        labels,
        [int(row["proof_bytes"]) for row in valid_rows],
        "Sapling Proof Sizes",
        "Proof Size (bytes)",
        FIGURE_DIR / "sapling_proof_size.png",
        formatter=lambda value: f"{value} B",
    )


# ============================================================
# 8. 主程序
# ============================================================


def main():
    print("=== Sapling 工程实验数据汇总 ===")
    print(f"仓库根目录：{ROOT}")
    print()

    scale_rows = summarize_scale()
    parameter_rows = summarize_parameters()
    performance_rows = summarize_performance()

    generate_scale_and_parameter_figures(
        scale_rows,
        parameter_rows,
    )

    generate_performance_figures(performance_rows)

    print()
    print("[DONE] 三张汇总表、七张图均已生成。")
    print("原始数据未被修改。")


if __name__ == "__main__":
    main()
