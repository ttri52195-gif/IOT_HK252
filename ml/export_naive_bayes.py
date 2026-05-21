#!/usr/bin/env python3
"""Train Gaussian Naive Bayes and export deployable C header.

Why not TFLite:
- Gaussian Naive Bayes is not a standard TensorFlow model, so TFLite export is not the right target.
- For ESP32, export the learned parameters as C arrays and implement the NB score function in firmware.

Outputs:
- naive_bayes_model.h            -> C arrays for deployment
- naive_bayes_metrics.json       -> accuracy + model metadata

Usage:
  python export_naive_bayes.py --input train_ready.csv --prefix naive_bayes_model
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent


@dataclass
class Dataset:
    x: np.ndarray
    y: np.ndarray
    labels: List[str]


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    return SCRIPT_DIR / path


def load_dataset(csv_path: Path) -> Dataset:
    temperatures: List[float] = []
    humidities: List[float] = []
    raw_labels: List[str] = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"temperature", "humidity", "label"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError("CSV must contain columns: temperature, humidity, label")

        for row in reader:
            temp_raw = (row.get("temperature") or "").strip()
            humi_raw = (row.get("humidity") or "").strip()
            label = (row.get("label") or "").strip()
            if not temp_raw or not humi_raw or not label:
                continue
            try:
                temp = float(temp_raw)
                humi = float(humi_raw)
            except ValueError:
                continue
            temperatures.append(temp)
            humidities.append(humi)
            raw_labels.append(label)

    if not raw_labels:
        raise ValueError("No valid rows found in training CSV")

    preferred_order = [
        "Không hợp lệ",
        "Chế độ chờ (Standby)",
        "Bật điều hòa",
        "Bật máy hút ẩm",
        "Bật máy phun sương",
    ]
    unique = set(raw_labels)
    labels = [name for name in preferred_order if name in unique]
    labels.extend(sorted(unique - set(labels)))
    label_to_index = {name: i for i, name in enumerate(labels)}

    x = np.column_stack((temperatures, humidities)).astype(np.float32)
    y = np.array([label_to_index[name] for name in raw_labels], dtype=np.int32)
    return Dataset(x=x, y=y, labels=labels)


def split_train_test(
    x: np.ndarray,
    y: np.ndarray,
    test_ratio: float,
    seed: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if not 0.0 < test_ratio < 1.0:
        raise ValueError("test_ratio must be in (0, 1)")

    rng = np.random.default_rng(seed)
    indices = np.arange(len(x))
    rng.shuffle(indices)

    test_size = max(1, int(len(indices) * test_ratio))
    test_idx = indices[:test_size]
    train_idx = indices[test_size:]

    if len(train_idx) == 0:
        raise ValueError("Train set is empty after split. Reduce test_ratio.")

    return x[train_idx], x[test_idx], y[train_idx], y[test_idx]


def zscore_fit_transform(x_train: np.ndarray, x_test: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    mean = x_train.mean(axis=0)
    std = x_train.std(axis=0)
    std = np.where(std < 1e-6, 1.0, std)

    x_train_n = (x_train - mean) / std
    x_test_n = (x_test - mean) / std
    return x_train_n.astype(np.float32), x_test_n.astype(np.float32), mean.astype(np.float32), std.astype(np.float32)


def train_naive_bayes(x_train_n: np.ndarray, y_train: np.ndarray, x_test_n: np.ndarray, y_test: np.ndarray):
    from sklearn.metrics import accuracy_score
    from sklearn.naive_bayes import GaussianNB

    model = GaussianNB()
    model.fit(x_train_n, y_train)

    train_acc = float(accuracy_score(y_train, model.predict(x_train_n)))
    test_acc = float(accuracy_score(y_test, model.predict(x_test_n)))
    return model, train_acc, test_acc


def export_c_header(
    path: Path,
    labels: List[str],
    mean: np.ndarray,
    std: np.ndarray,
    class_prior: np.ndarray,
    theta: np.ndarray,
    variance: np.ndarray,
    epsilon: float,
) -> None:
    n_classes = len(labels)
    n_features = 2

    label_lines = ", ".join(f'"{label}"' for label in labels)
    mean_lines = ", ".join(f"{float(v):.8f}f" for v in mean)
    std_lines = ", ".join(f"{float(v):.8f}f" for v in std)
    prior_lines = ", ".join(f"{float(v):.8f}f" for v in class_prior)
    epsilon_line = f"{float(epsilon):.10f}f"

    theta_rows = []
    variance_rows = []
    for i in range(n_classes):
        theta_rows.append("    {" + ", ".join(f"{float(v):.8f}f" for v in theta[i]) + "}")
        variance_rows.append("    {" + ", ".join(f"{float(v):.8f}f" for v in variance[i]) + "}")

    content = (
        "#ifndef NAIVE_BAYES_MODEL_H\n"
        "#define NAIVE_BAYES_MODEL_H\n\n"
        f"#define NB_NUM_CLASSES {n_classes}\n"
        f"#define NB_NUM_FEATURES {n_features}\n\n"
        f"static const char* kNbLabels[NB_NUM_CLASSES] = {{{label_lines}}};\n"
        f"static const float kNbFeatureMean[NB_NUM_FEATURES] = {{{mean_lines}}};\n"
        f"static const float kNbFeatureStd[NB_NUM_FEATURES] = {{{std_lines}}};\n"
        f"static const float kNbClassPrior[NB_NUM_CLASSES] = {{{prior_lines}}};\n"
        f"static const float kNbEpsilon = {epsilon_line};\n\n"
        "static const float kNbTheta[NB_NUM_CLASSES][NB_NUM_FEATURES] = {\n"
        + ",\n".join(theta_rows)
        + "\n};\n\n"
        "static const float kNbVariance[NB_NUM_CLASSES][NB_NUM_FEATURES] = {\n"
        + ",\n".join(variance_rows)
        + "\n};\n\n"
        "// Runtime formula on ESP32:\n"
        "// 1) normalize input: x_norm[j] = (x[j] - kNbFeatureMean[j]) / kNbFeatureStd[j]\n"
        "// 2) score[class] = log(prior) - 0.5 * sum(log(2*pi*var)) - 0.5 * sum((x_norm-theta)^2 / var)\n"
        "// 3) choose argmax(score)\n"
        "#endif\n"
    )
    path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Train Gaussian Naive Bayes and export C header")
    parser.add_argument("--input", default="train_ready.csv", help="Input CSV")
    parser.add_argument("--test-ratio", type=float, default=0.2, help="Test split ratio")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--prefix", default="naive_bayes_model", help="Output prefix")
    args = parser.parse_args()

    try:
        from sklearn.naive_bayes import GaussianNB  # noqa: F401
    except ImportError:
        print("scikit-learn is not installed. Install with: pip install scikit-learn")
        return 1

    input_path = resolve_path(args.input)
    if not input_path.exists():
        print(f"Input CSV not found: {input_path}")
        return 1

    dataset = load_dataset(input_path)
    x_train, x_test, y_train, y_test = split_train_test(dataset.x, dataset.y, args.test_ratio, args.seed)
    x_train_n, x_test_n, mean, std = zscore_fit_transform(x_train, x_test)

    model, train_acc, test_acc = train_naive_bayes(x_train_n, y_train, x_test_n, y_test)

    metrics_path = SCRIPT_DIR / f"{args.prefix}_metrics.json"
    header_path = SCRIPT_DIR / f"{args.prefix}.h"

    metrics = {
        "model_type": "GaussianNB",
        "train_accuracy": train_acc,
        "test_accuracy": test_acc,
        "labels": dataset.labels,
        "feature_order": ["temperature", "humidity"],
        "classes": model.classes_.tolist(),
        "class_prior": model.class_prior_.tolist(),
        "theta": model.theta_.tolist(),
        "variance": model.var_.tolist(),
        "epsilon": float(model.epsilon_),
        "zscore_mean": mean.tolist(),
        "zscore_std": std.tolist(),
    }
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    export_c_header(header_path, dataset.labels, mean, std, model.class_prior_, model.theta_, model.var_, model.epsilon_)

    print(f"[nb] train_accuracy={train_acc:.4f} test_accuracy={test_acc:.4f}")
    print(f"[export] saved metrics -> {metrics_path.name}")
    print(f"[export] saved C header -> {header_path.name}")
    print("[note] Naive Bayes is exported as C parameters, not TFLite.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
