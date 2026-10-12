from __future__ import annotations

import argparse
import csv
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

# Parameters are stored outside the Git repository.
# Priority: command-line argument > environment variable > default path.
DEFAULT_PARAM_DIR = Path(
    os.environ.get("ZCASH_PARAMS_DIR") or r"D:\Research\zcash-params"
)

OUTPUT_CSV = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "metadata"
    / "parameter_validation.csv"
)


# Official BLAKE2b-512 hashes from Zcash Protocol Specification, section 5.8.
# Each published hash consists of two consecutive 64-character hexadecimal lines.
PARAMS = {
    "sapling-spend.params": {
        "size": 47_958_396,
        "hash": (
            "8270785a1a0d0bc77196f000ee6d221c"
            "9c9894f55307bd9357c3f0105d31ca63"
            "991ab91324160d8f53e2bbd3c2633a6e"
            "b8bdf5205d822e7f3f73edac51b2b70c"
        ),
    },
    "sapling-output.params": {
        "size": 3_592_860,
        "hash": (
            "657e3d38dbb5cb5e7dd2970e8b03d69b"
            "4787dd907285b5a7f0790dcc8072f60b"
            "f593b32cc2d1c030e00ff5ae64bf84c5"
            "c3beb84ddc841d48264b4a171744d028"
        ),
    },
}


def blake2b512(path: Path) -> str:
    """Calculate BLAKE2b with a 512-bit digest, reading in chunks."""
    digest = hashlib.blake2b(digest_size=64)

    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Zcash Sapling parameter files."
    )
    parser.add_argument(
        "--param-dir",
        type=Path,
        default=DEFAULT_PARAM_DIR,
        help=(
            "Directory containing the Sapling parameter files. "
            "Can also be configured with ZCASH_PARAMS_DIR."
        ),
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=OUTPUT_CSV,
        help="Path for the validation report CSV.",
    )
    args = parser.parse_args()

    param_dir = args.param_dir.expanduser()
    output_csv = args.output_csv.expanduser()

    if not param_dir.is_dir():
        print(f"FAIL: parameter directory does not exist: {param_dir}")
        return 1

    print(f"Parameter directory: {param_dir.resolve()}")

    checked_at = datetime.now(timezone.utc).isoformat()
    rows = []
    all_passed = True

    for name, expected in PARAMS.items():
        path = param_dir / name

        if not path.is_file():
            print(f"\nFAIL: missing file: {path}")
            all_passed = False
            continue

        actual_size = path.stat().st_size
        actual_hash = blake2b512(path)

        size_ok = actual_size == expected["size"]
        hash_ok = actual_hash == expected["hash"]
        passed = size_ok and hash_ok
        all_passed &= passed

        status = "PASS" if passed else "FAIL"

        print(f"\n{name}")
        print(f"  Actual bytes: {actual_size:,}")
        print(f"  Expected bytes: {expected['size']:,}")
        print(f"  Size matches: {size_ok}")
        print(f"  BLAKE2b-512:  {actual_hash}")
        print(f"  Hash matches: {hash_ok}")
        print(f"  Status:       {status}")

        rows.append(
            {
                "checked_at_utc": checked_at,
                "file": name,
                "expected_bytes": expected["size"],
                "actual_bytes": actual_size,
                "expected_blake2b512": expected["hash"],
                "actual_blake2b512": actual_hash,
                "size_match": size_ok,
                "hash_match": hash_ok,
                "status": status,
            }
        )

    columns = [
        "checked_at_utc",
        "file",
        "expected_bytes",
        "actual_bytes",
        "expected_blake2b512",
        "actual_blake2b512",
        "size_match",
        "hash_match",
        "status",
    ]

    try:
        output_csv.parent.mkdir(parents=True, exist_ok=True)

        with output_csv.open(
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as file:
            writer = csv.DictWriter(file, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)

    except OSError as exc:
        print(f"\nFAIL: could not write validation report: {exc}")
        return 1

    print(f"\nValidation report: {output_csv.resolve()}")

    if not all_passed:
        print("RESULT: FAIL — do not use the parameters yet.")
        return 1

    print("RESULT: PASS — both parameter files are verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
