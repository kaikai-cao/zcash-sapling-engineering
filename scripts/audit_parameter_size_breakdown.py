import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = (
    ROOT
    / "experiments"
    / "raw"
    / "csv"
    / "sapling_parameter_size_breakdown_20261011_142729.csv"
)

EXPECTED_FILE_BYTES = {
    "Spend": 47_958_396,
    "Output": 3_592_860,
}

QUERY_SECTIONS = {
    "VK_IC",
    "H_G1",
    "L_G1",
    "A_G1",
    "B_G1",
    "B_G2",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    require(bool(rows), f"CSV 没有数据：{CSV_PATH}")

    for circuit, expected_bytes in EXPECTED_FILE_BYTES.items():
        circuit_rows = [
            row for row in rows if row["Circuit"] == circuit
        ]
        require(bool(circuit_rows), f"{circuit} 没有记录")

        circuit_rows.sort(key=lambda r: int(r["StartOffset"]))
        previous_end = 0

        print(f"\n===== {circuit} =====")

        for row in circuit_rows:
            section = row["Section"]
            count = int(row["ElementCount"])
            start = int(row["StartOffset"])
            end = int(row["EndOffset"])
            prefix = int(row["LengthFieldBytes"])
            payload = int(row["PayloadBytes"])
            encoded = int(row["EncodedBytes"])

            # 检查各段是否首尾相接，是否存在遗漏或重叠。
            require(
                start == previous_end,
                f"{circuit}/{section}: 偏移不连续，"
                f"前一段结束={previous_end}，本段开始={start}",
            )
            require(
                end - start == encoded,
                f"{circuit}/{section}: 起止偏移与编码长度不一致",
            )
            require(
                encoded == payload + prefix,
                f"{circuit}/{section}: payload + prefix 不等于编码长度",
            )

            # 检查每项内容的数量与字节数是否相符。
            if section in QUERY_SECTIONS:
                point_bytes = int(row["PointEncodingBytes"])
                expected_payload = count * point_bytes

                require(
                    payload == expected_payload,
                    f"{circuit}/{section}: 点数量 × 单点大小不匹配",
                )

            elif section == "VK_FIXED_POINTS":
                # 3 个 G1 点 + 3 个 G2 点。
                expected_payload = 3 * 96 + 3 * 192
                require(
                    count == 6 and payload == expected_payload,
                    f"{circuit}/{section}: 固定 VK 点数量或大小错误",
                )

            elif section == "MPC_CIRCUIT_HASH":
                require(payload == 64, "MPC 电路哈希应为 64 bytes")

            elif section == "MPC_CONTRIBUTOR_COUNT":
                require(prefix == 4 and encoded == 4,
                        "MPC 贡献者数量字段应为 4 bytes")

            elif section == "MPC_CONTRIBUTION_RECORDS":
                # 每条记录 = 3×G1 + 1×G2 + 64-byte transcript。
                bytes_per_record = 3 * 96 + 192 + 64
                require(
                    count == 97
                    and payload == count * bytes_per_record,
                    f"{circuit}/{section}: MPC 记录大小错误",
                )

            print(
                f"{section:24s} "
                f"count={count:>7,} "
                f"payload={payload:>10,} B "
                f"prefix={prefix:>2} B "
                f"encoded={encoded:>10,} B"
            )

            previous_end = end

        actual_bytes = sum(
            int(row["EncodedBytes"]) for row in circuit_rows
        )

        require(
            previous_end == expected_bytes,
            f"{circuit}: 最终偏移 {previous_end:,} "
            f"不等于文件大小 {expected_bytes:,}",
        )
        require(
            actual_bytes == expected_bytes,
            f"{circuit}: 各段累计 {actual_bytes:,} "
            f"不等于文件大小 {expected_bytes:,}",
        )

        print(f"PASS: {circuit} = {actual_bytes:,} bytes")

    print("\n所有参数文件的字节账均通过检查。")


if __name__ == "__main__":
    main()