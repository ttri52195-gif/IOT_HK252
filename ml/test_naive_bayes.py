#!/usr/bin/env python3
"""Interactive tester for the exported Gaussian Naive Bayes model.

This script uses the exported metrics JSON from export_naive_bayes.py to
reproduce the same prediction logic on PC before deploying to ESP32.

Usage:
  python test_naive_bayes.py --model naive_bayes_model_metrics.json
  python test_naive_bayes.py --model naive_bayes_model_metrics.json --temperature 26.5 --humidity 48.0
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import List

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    # If the user passed a multi-segment relative path (e.g. 'ml/naive_bayes_model_metrics.json')
    # we should treat it as relative to the current working directory to avoid producing
    # SCRIPT_DIR / 'ml/...' which becomes 'ml/ml/...'. For plain filenames, keep them
    # beside the script directory.
    if path.parent != Path('.'):
        return Path(path_str)
    return SCRIPT_DIR / path


def load_model(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def softmax(logits: np.ndarray) -> np.ndarray:
    logits = logits - np.max(logits)
    exp = np.exp(logits)
    return exp / np.sum(exp)


def predict(
    temperature: float,
    humidity: float,
    model_data: dict,
) -> tuple[str, float, List[tuple[str, float]]]:
    labels = model_data["labels"]
    mean = np.array(model_data["zscore_mean"], dtype=np.float32)
    std = np.array(model_data["zscore_std"], dtype=np.float32)
    class_prior = np.array(model_data["class_prior"], dtype=np.float32)
    theta = np.array(model_data["theta"], dtype=np.float32)
    variance = np.array(model_data["variance"], dtype=np.float32)
    epsilon = float(model_data.get("epsilon", 1e-9))

    x = np.array([temperature, humidity], dtype=np.float32)
    x_norm = (x - mean) / np.where(std < 1e-6, 1.0, std)

    # Gaussian Naive Bayes log likelihood.
    var = variance + epsilon
    log_prior = np.log(np.clip(class_prior, 1e-12, None))
    log_det = -0.5 * np.sum(np.log(2.0 * math.pi * var), axis=1)
    quad = -0.5 * np.sum(((x_norm - theta) ** 2) / var, axis=1)
    logits = log_prior + log_det + quad
    probs = softmax(logits)

    best_idx = int(np.argmax(probs))
    ranked = sorted(zip(labels, probs.tolist()), key=lambda item: item[1], reverse=True)
    return labels[best_idx], float(probs[best_idx]), ranked


def prompt_float(name: str) -> float:
    while True:
        raw = input(f"Nhap {name}: ").strip()
        try:
            return float(raw)
        except ValueError:
            print("Gia tri khong hop le, vui long nhap so.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive tester for Gaussian Naive Bayes")
    parser.add_argument("--model", default="naive_bayes_model_metrics.json", help="Exported metrics JSON")
    parser.add_argument("--temperature", type=float, default=None, help="Temperature value")
    parser.add_argument("--humidity", type=float, default=None, help="Humidity value")
    parser.add_argument("--top-k", type=int, default=3, help="How many top predictions to print")
    args = parser.parse_args()

    model_path = resolve_path(args.model)
    if not model_path.exists():
        print(f"Model file not found: {model_path}")
        return 1

    model_data = load_model(model_path)

    temperature = args.temperature if args.temperature is not None else prompt_float("nhiệt độ (°C)")
    humidity = args.humidity if args.humidity is not None else prompt_float("độ ẩm (%)")

    label, confidence, ranked = predict(temperature, humidity, model_data)

    print("\n=== Ket qua du doan ===")
    print(f"Input: T={temperature:.2f} °C, H={humidity:.2f} %")
    print(f"Predicted label: {label}")
    print(f"Confidence: {confidence:.4f}")

    print("\nTop predictions:")
    for idx, (name, prob) in enumerate(ranked[: max(1, args.top_k)], start=1):
        print(f"  {idx}. {name}: {prob:.4f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
