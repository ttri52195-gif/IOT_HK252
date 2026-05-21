#!/usr/bin/env python3
"""Append synthetic raw samples focused on AC-on condition.

Target rule from extract_ready_data.py:
- AC on when temperature > 33 and 50 <= humidity <= 80
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

# Sample configuration
num_ac_core = 1800
num_ac_boundary = 700
num_non_ac_nearby = 500

rng = np.random.default_rng(seed=252)


def make_rows() -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []

    # 1) Core AC region: comfortably inside rule domain
    ac_core_t = rng.uniform(34.0, 39.5, num_ac_core)
    ac_core_h = rng.uniform(54.0, 76.0, num_ac_core)

    # 2) AC boundary region: close to rule edges to improve decision boundaries
    ac_bnd_t = rng.uniform(33.01, 34.2, num_ac_boundary)
    ac_bnd_h = rng.uniform(50.0, 80.0, num_ac_boundary)

    # 3) Nearby but non-AC points (hard negatives)
    # Half: temp > 33, hum just below 50 (Normal)
    half = num_non_ac_nearby // 2
    neg1_t = rng.uniform(33.2, 36.0, half)
    neg1_h = rng.uniform(45.0, 49.95, half)

    # Half: temp > 33, hum just above 80 (Dehumidifier)
    neg2_t = rng.uniform(33.2, 36.0, num_non_ac_nearby - half)
    neg2_h = rng.uniform(80.05, 88.0, num_non_ac_nearby - half)

    temps = np.concatenate([ac_core_t, ac_bnd_t, neg1_t, neg2_t])
    humis = np.concatenate([ac_core_h, ac_bnd_h, neg1_h, neg2_h])

    # Slight shuffle while keeping pair alignment
    idx = rng.permutation(len(temps))
    temps = temps[idx]
    humis = humis[idx]

    start = datetime.utcnow()
    for i, (t, h) in enumerate(zip(temps, humis)):
        ts = (start + timedelta(milliseconds=i * 100)).isoformat() + "Z"
        t_s = f"{t:.4f}"
        h_s = f"{h:.4f}"
        raw = f"T={t_s} H={h_s}"
        rows.append((ts, t_s, h_s, raw))

    return rows


def main() -> int:
    output = Path(__file__).resolve().parent / "raw_data.csv"
    if not output.exists():
        print(f"[error] file not found: {output}")
        return 1

    rows = make_rows()

    with output.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    print(f"[append] added rows: {len(rows)}")
    print(f"[append] output file: {output.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
