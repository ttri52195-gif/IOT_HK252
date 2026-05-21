#!/usr/bin/env python3
"""Collect temperature/humidity samples from ESP32 serial log into raw_data.csv.

Example:
    python collect_from_log.py --port COM4 --baud 115200 --output raw_data.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

T_H_PATTERN = re.compile(r"T\s*=\s*([-+]?\d+(?:\.\d+)?)\D+H\s*=\s*([-+]?\d+(?:\.\d+)?)", re.IGNORECASE)
SCRIPT_DIR = Path(__file__).resolve().parent


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_temp_humi_from_line(line: str) -> Optional[Tuple[float, float]]:
    text = (line or "").strip()
    if not text:
        return None

    # JSON format: {"temperature": 29.8, "humidity": 67.1}
    if text.startswith("{") and text.endswith("}"):
        try:
            data = json.loads(text)
            if "temperature" in data and "humidity" in data:
                return float(data["temperature"]), float(data["humidity"])
        except (ValueError, TypeError, json.JSONDecodeError):
            pass

    # Key-value format: "... T=31.77 H=63.31"
    match = T_H_PATTERN.search(text)
    if match:
        return float(match.group(1)), float(match.group(2))

    # CSV-ish fallback: "...,31.77,63.31"
    parts = [p.strip() for p in text.split(",")]
    if len(parts) >= 2:
        try:
            return float(parts[-2]), float(parts[-1])
        except ValueError:
            return None

    return None


def ensure_header(csv_path: Path) -> None:
    if csv_path.exists() and csv_path.stat().st_size > 0:
        return

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["timestamp", "temperature", "humidity", "raw_line"],
        )
        writer.writeheader()


def resolve_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return SCRIPT_DIR / path


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect temperature/humidity from serial log")
    parser.add_argument("--port", required=True, help="Serial port, for example COM4")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
    parser.add_argument("--output", default="raw_data.csv", help="Output CSV path")
    parser.add_argument("--duration-sec", type=int, default=0, help="0 = run until Ctrl+C")
    args = parser.parse_args()

    try:
        import serial  # type: ignore
    except ImportError:
        print("Missing dependency: pyserial. Install with: pip install pyserial", file=sys.stderr)
        return 1

    output_path = resolve_path(args.output)
    ensure_header(output_path)

    print(f"[collect] Open serial {args.port} @ {args.baud}")
    print(f"[collect] Writing parsed samples to: {output_path.as_posix()}")
    print("[collect] Press Ctrl+C to stop.")

    started = time.monotonic()
    rows_written = 0

    try:
        with serial.Serial(args.port, args.baud, timeout=1) as ser, output_path.open(
            "a", encoding="utf-8", newline=""
        ) as f:
            writer = csv.DictWriter(f, fieldnames=["timestamp", "temperature", "humidity", "raw_line"])

            while True:
                if args.duration_sec > 0 and (time.monotonic() - started) >= args.duration_sec:
                    break

                raw = ser.readline().decode(errors="ignore").strip()
                if not raw:
                    continue

                parsed = parse_temp_humi_from_line(raw)
                if parsed is None:
                    continue

                temperature, humidity = parsed
                writer.writerow(
                    {
                        "timestamp": now_iso(),
                        "temperature": f"{temperature:.4f}",
                        "humidity": f"{humidity:.4f}",
                        "raw_line": f"T={temperature:.4f} H={humidity:.4f}",
                    }
                )
                f.flush()
                rows_written += 1

                if rows_written % 20 == 0:
                    print(f"[collect] Parsed and saved {rows_written} samples")

    except KeyboardInterrupt:
        print("\n[collect] Stopped by user.")
    except Exception as exc:  # noqa: BLE001
        print(f"[collect] Error: {exc}", file=sys.stderr)
        return 1

    print(f"[collect] Done. Total samples written: {rows_written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
