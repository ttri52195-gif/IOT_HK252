#!/usr/bin/env python3
"""Generate additional raw data samples with uniform distribution.

Generates 8000 samples with:
- Temperature: uniformly distributed from 0 to 100°C
- Humidity: uniformly distributed from 0 to 100%

Appends to raw_data.csv

Usage:
  python generate_additional_data.py --output raw_data.csv --count 8000
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent


def generate_samples(count: int, seed: int = 42) -> list:
    """Generate random samples with uniform distribution."""
    rng = np.random.default_rng(seed)
    
    temperatures = rng.uniform(0, 100, count)
    humidities = rng.uniform(0, 100, count)
    
    samples = []
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    for temp, humid in zip(temperatures, humidities):
        sample = {
            "timestamp": timestamp,
            "temperature": f"{temp:.4f}",
            "humidity": f"{humid:.4f}",
            "raw_line": f"T={temp:.4f} H={humid:.4f}"
        }
        samples.append(sample)
    
    return samples


def append_to_csv(csv_path: Path, samples: list):
    """Append samples to existing CSV file."""
    fieldnames = ["timestamp", "temperature", "humidity", "raw_line"]
    
    # Check if file exists and has content
    file_exists = csv_path.exists() and csv_path.stat().st_size > 0
    
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        # Write header if file is empty
        if not file_exists:
            writer.writeheader()
        
        writer.writerows(samples)
    
    print(f"✓ Added {len(samples)} samples to {csv_path}")
    print(f"✓ File size: {csv_path.stat().st_size / 1024:.2f} KB")


def main():
    parser = argparse.ArgumentParser(
        description="Generate additional raw data samples with uniform distribution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output",
        type=str,
        default="raw_data.csv",
        help="Output CSV file (default: raw_data.csv)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=8000,
        help="Number of samples to generate (default: 8000)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )
    parser.add_argument(
        "--temp-min",
        type=float,
        default=0.0,
        help="Minimum temperature (default: 0.0)",
    )
    parser.add_argument(
        "--temp-max",
        type=float,
        default=100.0,
        help="Maximum temperature (default: 100.0)",
    )
    parser.add_argument(
        "--humid-min",
        type=float,
        default=0.0,
        help="Minimum humidity (default: 0.0)",
    )
    parser.add_argument(
        "--humid-max",
        type=float,
        default=100.0,
        help="Maximum humidity (default: 100.0)",
    )

    args = parser.parse_args()

    # Resolve paths
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = SCRIPT_DIR / output_path

    print(f"Generating {args.count} samples...")
    print(f"  Temperature range: {args.temp_min}°C to {args.temp_max}°C")
    print(f"  Humidity range: {args.humid_min}% to {args.humid_max}%")
    print()

    # Generate samples with custom ranges
    rng = np.random.default_rng(args.seed)
    temperatures = rng.uniform(args.temp_min, args.temp_max, args.count)
    humidities = rng.uniform(args.humid_min, args.humid_max, args.count)

    samples = []
    timestamp = datetime.utcnow().isoformat() + "Z"

    for temp, humid in zip(temperatures, humidities):
        sample = {
            "timestamp": timestamp,
            "temperature": f"{temp:.4f}",
            "humidity": f"{humid:.4f}",
            "raw_line": f"T={temp:.4f} H={humid:.4f}"
        }
        samples.append(sample)

    # Append to CSV
    append_to_csv(output_path, samples)

    print("\n" + "=" * 70)
    print("✓ Data generation completed successfully!")
    print(f"  Location: {output_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
