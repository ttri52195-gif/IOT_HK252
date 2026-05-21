#!/usr/bin/env python3
"""Extract train-ready data from raw_data.csv using fixed labeling rules.

Input  columns: timestamp, temperature, humidity, raw_line
Output columns: temperature, humidity, label

Default output includes class "Không hợp lệ".
Example:
    python extract_ready_data.py --input raw_data.csv --output train_ready.csv
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

LABEL_INVALID = "Không hợp lệ"
LABEL_NORMAL = "Chế độ bình thường"
LABEL_AC = "Bật điều hòa"
LABEL_DEHUMIDIFIER = "Bật máy hút ẩm"
LABEL_HEATER = "Bật máy sưởi"
SCRIPT_DIR = Path(__file__).resolve().parent


def classify_label(temp: float, humi: float) -> str:
    # Dữ liệu không hợp lệ.
    if temp < 0.0 or temp > 100.0 or humi < 0.0 or humi > 100.0:
        return LABEL_INVALID

    # Máy sưởi: nhiệt độ nhỏ hơn 24.
    elif temp < 24.0:
        return LABEL_HEATER

    # Bật điều hòa: nhiệt độ lớn hơn 33, độ ẩm 50-80.
    elif temp > 33.0 and  humi <= 80.0:
        return LABEL_AC

    # Máy hút ẩm: nhiệt độ lớn hơn 33, độ ẩm lớn hơn 80.
    elif temp > 33.0 and humi > 80.0:
        return LABEL_DEHUMIDIFIER

    # Chế độ bình thường mặc định cho mọi dữ liệu còn lại trong miền hợp lệ.
    else:
        return LABEL_NORMAL


def parse_float(value: str) -> float | None:
    try:
        return float((value or "").strip())
    except ValueError:
        return None


def resolve_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    # If user provided a path that includes a parent (e.g. 'ml/raw_data.csv'),
    # interpret it as relative to the current working directory instead of
    # joining again with the script directory which would produce 'ml/ml/...'.
    if path.parent != Path('.'):
        return Path(value)

    # For plain filenames (no parent), treat them as located beside the script.
    return SCRIPT_DIR / path


def resolve_output_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return SCRIPT_DIR / path.name


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract training data from raw CSV")
    parser.add_argument("--input", default="raw_data.csv", help="Raw input CSV")
    parser.add_argument(
        "--output",
        default="train_ready.csv",
        help="Output train CSV. Relative paths are written beside this script as a single file name.",
    )
    parser.add_argument(
        "--include-invalid",
        action="store_true",
        default=True,
        help="Include label 'Không hợp lệ' in output (default: true)",
    )
    parser.add_argument(
        "--exclude-invalid",
        action="store_true",
        help="Exclude rows with label 'Không hợp lệ'",
    )
    args = parser.parse_args()

    include_invalid = args.include_invalid and not args.exclude_invalid

    input_path = resolve_path(args.input)
    output_path = resolve_output_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    counter = Counter()
    total = 0
    written = 0

    with input_path.open("r", encoding="utf-8-sig", newline="") as f_in, output_path.open(
        "w", encoding="utf-8", newline=""
    ) as f_out:
        reader = csv.DictReader(f_in)
        writer = csv.DictWriter(f_out, fieldnames=["temperature", "humidity", "label"])
        writer.writeheader()

        for row in reader:
            total += 1
            temp = parse_float(str(row.get("temperature", "")))
            humi = parse_float(str(row.get("humidity", "")))

            if temp is None or humi is None:
                label = LABEL_INVALID
            else:
                label = classify_label(temp, humi)

            if label == LABEL_INVALID and not include_invalid:
                continue

            writer.writerow(
                {
                    "temperature": row.get("temperature", ""),
                    "humidity": row.get("humidity", ""),
                    "label": label,
                }
            )
            written += 1
            counter[label] += 1

    print(f"[extract] input rows:  {total}")
    print(f"[extract] output rows: {written}")
    print(f"[extract] output file: {output_path.as_posix()}")
    print("[extract] label distribution:")
    for label, count in counter.most_common():
        print(f"  - {label}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
