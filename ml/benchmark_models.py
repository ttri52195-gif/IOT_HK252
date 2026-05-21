#!/usr/bin/env python3
"""Benchmark classification models for ESP32 deployment.

Compares:
- MLP (TensorFlow/Keras -> h5, tflite size)
- Random Forest
- Gaussian Naive Bayes
- SVM (RBF)

Metrics:
- train/test accuracy
- artifact size
- average prediction latency on test set
- model complexity hints

Usage:
    python benchmark_models.py --mode benchmark --input train_ready.csv --prefix benchmark
    python benchmark_models.py --mode evaluate --input train_ready.csv --output evaluation_results.json
"""

from __future__ import annotations

import argparse
import csv
import json
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent


@dataclass
class Dataset:
    x: np.ndarray
    y: np.ndarray
    labels: List[str]


@dataclass
class BenchmarkResult:
    model_name: str
    train_accuracy: float
    test_accuracy: float
    artifact_size_bytes: int
    avg_inference_ms: float
    note: str


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


def build_mlp(num_classes: int):
    import tensorflow as tf

    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=(2,), name="sensor_input"),
            tf.keras.layers.Dense(16, activation="relu"),
            tf.keras.layers.Dense(16, activation="relu"),
            tf.keras.layers.Dense(num_classes, activation="softmax", name="class_output"),
        ]
    )
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )

    tf.keras.utils.plot_model(
        model,
        to_file="mlp_architecture.png", # Tên file ảnh xuất ra
        show_shapes=True,               # Hiện kích thước (ví dụ: None, 2)
        show_layer_names=True,          # Hiện tên layer
        show_layer_activations=True,    # Hiện hàm kích hoạt (relu, softmax)
        dpi=300                         # Độ phân giải cao để in báo cáo
    )
    
    return model


def representative_dataset(x_train: np.ndarray):
    for i in range(min(len(x_train), 300)):
        yield [x_train[i : i + 1].astype(np.float32)]


def mlp_metrics(x_train_n: np.ndarray, y_train: np.ndarray, x_test_n: np.ndarray, y_test: np.ndarray, epochs: int, batch_size: int, seed: int, num_classes: int) -> Tuple[BenchmarkResult, Dict[str, List[float]], object]:
    import tensorflow as tf

    tf.keras.utils.set_random_seed(seed)
    model = build_mlp(num_classes)
    history = model.fit(
        x_train_n,
        y_train,
        validation_split=0.2,
        epochs=epochs,
        batch_size=batch_size,
        verbose=0,
    )

    train_loss, train_acc = model.evaluate(x_train_n, y_train, verbose=0)
    test_loss, test_acc = model.evaluate(x_test_n, y_test, verbose=0)

    # Measure artifact size using .h5 and .tflite (the latter is the deploy target).
    with tempfile.TemporaryDirectory() as tmpdir:
        h5_path = Path(tmpdir) / "mlp.h5"
        tflite_path = Path(tmpdir) / "mlp_int8.tflite"
        model.save(h5_path, include_optimizer=False)

        converter = tf.lite.TFLiteConverter.from_keras_model(model)
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.representative_dataset = lambda: representative_dataset(x_train_n)
        converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
        converter.inference_input_type = tf.int8
        converter.inference_output_type = tf.int8
        tflite_path.write_bytes(converter.convert())

        artifact_size = tflite_path.stat().st_size

    result = BenchmarkResult(
        model_name="MLP (TFLite INT8)",
        train_accuracy=float(train_acc),
        test_accuracy=float(test_acc),
        artifact_size_bytes=artifact_size,
        avg_inference_ms=measure_latency(model, x_test_n),
        note=f"validation_accuracy={history.history.get('val_accuracy', [0.0])[-1]:.4f}; train_loss={train_loss:.4f}; test_loss={test_loss:.4f}",
    )
    return result, history.history, model


def measure_latency(model, x_test_n: np.ndarray, sample_count: int = 128) -> float:
    count = min(sample_count, len(x_test_n))
    samples = x_test_n[:count]
    if count == 0:
        return 0.0

    # Warm-up for Keras/sklearn models.
    if hasattr(model, "predict"):
        model.predict(samples[:1], verbose=0) if "tensorflow" in str(type(model)).lower() else model.predict(samples[:1])

    start = time.perf_counter()
    if "tensorflow" in str(type(model)).lower():
        _ = model.predict(samples, verbose=0)
    else:
        _ = model.predict(samples)
    elapsed = time.perf_counter() - start
    return (elapsed * 1000.0) / count


def train_random_forest(x_train_n: np.ndarray, y_train: np.ndarray, x_test_n: np.ndarray, y_test: np.ndarray, seed: int, n_estimators: int, max_depth: int):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score

    model = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth if max_depth > 0 else None,
        random_state=seed,
        n_jobs=-1,
    )
    model.fit(x_train_n, y_train)
    train_acc = float(accuracy_score(y_train, model.predict(x_train_n)))
    test_acc = float(accuracy_score(y_test, model.predict(x_test_n)))
    return model, train_acc, test_acc


def train_naive_bayes(x_train_n: np.ndarray, y_train: np.ndarray, x_test_n: np.ndarray, y_test: np.ndarray):
    from sklearn.metrics import accuracy_score
    from sklearn.naive_bayes import GaussianNB

    model = GaussianNB()
    model.fit(x_train_n, y_train)
    train_acc = float(accuracy_score(y_train, model.predict(x_train_n)))
    test_acc = float(accuracy_score(y_test, model.predict(x_test_n)))
    return model, train_acc, test_acc


def train_svm(x_train_n: np.ndarray, y_train: np.ndarray, x_test_n: np.ndarray, y_test: np.ndarray, seed: int, svm_c: float):
    from sklearn.metrics import accuracy_score
    from sklearn.svm import SVC

    model = SVC(kernel="rbf", C=svm_c, gamma="scale", probability=False, random_state=seed)
    model.fit(x_train_n, y_train)
    train_acc = float(accuracy_score(y_train, model.predict(x_train_n)))
    test_acc = float(accuracy_score(y_test, model.predict(x_test_n)))
    return model, train_acc, test_acc


def estimate_model_size_bytes(model, artifact_path: Path | None = None) -> int:
    if artifact_path and artifact_path.exists():
        return artifact_path.stat().st_size
    try:
        import joblib

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir) / "model.joblib"
            joblib.dump(model, temp_path)
            return temp_path.stat().st_size
    except Exception:
        return 0


def write_csv(path: Path, rows: List[BenchmarkResult]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["model_name", "train_accuracy", "test_accuracy", "artifact_size_bytes", "avg_inference_ms", "note"])
        for row in rows:
            writer.writerow([
                row.model_name,
                f"{row.train_accuracy:.6f}",
                f"{row.test_accuracy:.6f}",
                row.artifact_size_bytes,
                f"{row.avg_inference_ms:.6f}",
                row.note,
            ])


def calculate_esp32_scores(results: List[BenchmarkResult]) -> Dict[str, float]:
    if not results:
        return {}

    accuracies = [r.test_accuracy for r in results]
    latencies = [r.avg_inference_ms for r in results]

    max_accuracy = max(accuracies) if accuracies else 1.0
    max_latency = max(latencies) if latencies else 1.0

    scores: Dict[str, float] = {}
    for row in results:
        size_kb = row.artifact_size_bytes / 1024.0

        # Accuracy score (0-40): higher is better.
        acc_score = (row.test_accuracy / max_accuracy) * 40.0 if max_accuracy > 0 else 0.0

        # Size score (0-30): ideal <100KB, poor >1000KB.
        size_normalized = min(size_kb / 100.0, 10.0)
        size_score = (1.0 - min(size_normalized / 10.0, 1.0)) * 30.0

        # Speed score (0-30): lower latency is better.
        speed_score = (1.0 - (row.avg_inference_ms / max_latency)) * 30.0 if max_latency > 0 else 30.0

        scores[row.model_name] = acc_score + size_score + speed_score

    return scores


def plot_results(results: List[BenchmarkResult], accuracy_path: Path, size_path: Path, latency_path: Path, esp32_score_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    model_names = [r.model_name for r in results]
    test_accs_pct = [r.test_accuracy * 100.0 for r in results]
    sizes_kb = [r.artifact_size_bytes / 1024.0 for r in results]
    latencies = [r.avg_inference_ms for r in results]
    esp32_scores = calculate_esp32_scores(results)
    esp32_values = [esp32_scores.get(name, 0.0) for name in model_names]

    for p in (accuracy_path, size_path, latency_path, esp32_score_path):
        p.parent.mkdir(parents=True, exist_ok=True)

    fig_acc, ax_acc = plt.subplots(figsize=(7, 5), dpi=140)
    bars0 = ax_acc.bar(model_names, test_accs_pct, color="#1f77b4")
    ax_acc.set_title("Test Accuracy")
    ax_acc.set_xlabel("Model")
    ax_acc.set_ylabel("Accuracy (%)")
    ax_acc.set_ylim(0.0, 105.0)
    ax_acc.tick_params(axis="x", rotation=25)
    ax_acc.bar_label(bars0, fmt="%.1f%%")
    fig_acc.tight_layout()
    fig_acc.savefig(accuracy_path)
    plt.close(fig_acc)

    fig_size, ax_size = plt.subplots(figsize=(7, 5), dpi=140)
    bars1 = ax_size.bar(model_names, sizes_kb, color="#ff7f0e")
    ax_size.set_title("Artifact Size")
    ax_size.set_xlabel("Model")
    ax_size.set_ylabel("Size (KB)")
    ax_size.tick_params(axis="x", rotation=25)
    ax_size.bar_label(bars1, fmt="%.1f KB")
    fig_size.tight_layout()
    fig_size.savefig(size_path)
    plt.close(fig_size)

    fig_lat, ax_lat = plt.subplots(figsize=(7, 5), dpi=140)
    bars2 = ax_lat.bar(model_names, latencies, color="#2ca02c")
    ax_lat.set_title("Average Inference Time")
    ax_lat.set_xlabel("Model")
    ax_lat.set_ylabel("Latency (ms/sample)")
    ax_lat.tick_params(axis="x", rotation=25)
    ax_lat.bar_label(bars2, fmt="%.3f ms")
    fig_lat.tight_layout()
    fig_lat.savefig(latency_path)
    plt.close(fig_lat)

    fig_esp, ax_esp = plt.subplots(figsize=(7, 5), dpi=140)
    bars3 = ax_esp.bar(model_names, esp32_values, color="#d62728")
    ax_esp.set_title("ESP32 Suitability Score")
    ax_esp.set_xlabel("Model")
    ax_esp.set_ylabel("ESP32 Score (0-100)")
    ax_esp.set_ylim(0.0, 100.0)
    ax_esp.tick_params(axis="x", rotation=25)
    ax_esp.bar_label(bars3, fmt="%.2f")
    fig_esp.tight_layout()
    fig_esp.savefig(esp32_score_path)
    plt.close(fig_esp)


def pick_best_model(results: List[BenchmarkResult]) -> BenchmarkResult:
    # Prefer high accuracy, then smaller size, then lower latency.
    return sorted(results, key=lambda r: (-r.test_accuracy, r.artifact_size_bytes, r.avg_inference_ms))[0]


def run_comprehensive_evaluation(input_path: Path, test_size: float, seed: int, cv_folds: int, output_path: Path, visualizations: bool) -> int:
    from evaluate_models_comprehensive import ModelEvaluator

    evaluator = ModelEvaluator(test_size=test_size, random_state=seed, cv_folds=cv_folds)
    evaluator.run_evaluation(input_path)
    evaluator.generate_comparison_table()
    evaluator.print_esp32_ranking()
    evaluator.print_summary()
    evaluator.export_results(output_path)

    if visualizations:
        try:
            evaluator.generate_visualizations(input_path, output_path.parent)
        except Exception as exc:
            print(f"Warning: Could not generate visualizations: {exc}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark models for ESP32 deployment or run comprehensive evaluation")
    parser.add_argument("--mode", choices=["benchmark", "evaluate"], default="benchmark", help="What workflow to run")
    parser.add_argument("--input", default="train_ready.csv", help="Input training CSV")

    parser.add_argument("--test-size", type=float, default=0.2, help="Evaluation test set ratio")
    parser.add_argument("--output", default="evaluation_results.json", help="Evaluation output JSON file")
    parser.add_argument("--cv-folds", type=int, default=5, help="Evaluation cross-validation folds")
    parser.add_argument("--visualizations", action="store_true", help="Generate evaluation visualization plots")

    parser.add_argument("--test-ratio", type=float, default=0.2, help="Test split ratio")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--epochs", type=int, default=25, help="MLP training epochs")
    parser.add_argument("--batch-size", type=int, default=32, help="MLP batch size")
    parser.add_argument("--forest-trees", type=int, default=200, help="Random Forest trees")
    parser.add_argument("--forest-max-depth", type=int, default=0, help="Random Forest max depth, 0 = unlimited")
    parser.add_argument("--svm-c", type=float, default=10.0, help="SVM C parameter")
    parser.add_argument("--prefix", default="benchmark", help="Output file prefix")
    args = parser.parse_args()

    if args.mode == "evaluate":
        input_path = resolve_path(args.input)
        if not input_path.exists():
            print(f"Input CSV not found: {input_path}")
            return 1

        output_path = resolve_path(args.output)
        return run_comprehensive_evaluation(
            input_path=input_path,
            test_size=args.test_size,
            seed=args.seed,
            cv_folds=args.cv_folds,
            output_path=output_path,
            visualizations=args.visualizations,
        )

    try:
        import tensorflow as tf  # noqa: F401
    except ImportError:
        print("TensorFlow is not installed. Install with: pip install tensorflow")
        return 1

    try:
        import sklearn  # noqa: F401
    except ImportError:
        print("scikit-learn is not installed. Install with: pip install scikit-learn")
        return 1

    input_path = resolve_path(args.input)
    if not input_path.exists():
        print(f"Input CSV not found: {input_path}")
        return 1

    dataset = load_dataset(input_path)
    x_train, x_test, y_train, y_test = split_train_test(dataset.x, dataset.y, args.test_ratio, args.seed)
    x_train_n, x_test_n, _, _ = zscore_fit_transform(x_train, x_test)

    results: List[BenchmarkResult] = []
    artifacts_dir = SCRIPT_DIR

    # MLP
    mlp_result, mlp_history, mlp_model = mlp_metrics(x_train_n, y_train, x_test_n, y_test, args.epochs, args.batch_size, args.seed, len(dataset.labels))
    mlp_h5 = artifacts_dir / f"{args.prefix}_mlp.h5"
    mlp_tflite = artifacts_dir / f"{args.prefix}_mlp_int8.tflite"
    mlp_model.save(mlp_h5, include_optimizer=False)
    import tensorflow as tf
    converter = tf.lite.TFLiteConverter.from_keras_model(mlp_model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = lambda: representative_dataset(x_train_n)
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    mlp_tflite.write_bytes(converter.convert())
    mlp_result.artifact_size_bytes = mlp_tflite.stat().st_size
    results.append(mlp_result)

    # Random Forest
    rf_model, rf_train_acc, rf_test_acc = train_random_forest(x_train_n, y_train, x_test_n, y_test, args.seed, args.forest_trees, args.forest_max_depth)
    rf_path = artifacts_dir / f"{args.prefix}_forest.joblib"
    try:
        import joblib
        joblib.dump(rf_model, rf_path)
    except Exception:
        pass
    rf_result = BenchmarkResult(
        model_name="Random Forest",
        train_accuracy=rf_train_acc,
        test_accuracy=rf_test_acc,
        artifact_size_bytes=estimate_model_size_bytes(rf_model, rf_path),
        avg_inference_ms=measure_latency(rf_model, x_test_n),
        note=f"trees={args.forest_trees}; max_depth={args.forest_max_depth if args.forest_max_depth > 0 else 'unlimited'}; feature_importance={[float(v) for v in rf_model.feature_importances_]}",
    )
    results.append(rf_result)

    # Naive Bayes
    nb_model, nb_train_acc, nb_test_acc = train_naive_bayes(x_train_n, y_train, x_test_n, y_test)
    nb_path = artifacts_dir / f"{args.prefix}_naive_bayes.joblib"
    try:
        import joblib
        joblib.dump(nb_model, nb_path)
    except Exception:
        pass
    nb_result = BenchmarkResult(
        model_name="Naive Bayes",
        train_accuracy=nb_train_acc,
        test_accuracy=nb_test_acc,
        artifact_size_bytes=estimate_model_size_bytes(nb_model, nb_path),
        avg_inference_ms=measure_latency(nb_model, x_test_n),
        note="GaussianNB",
    )
    results.append(nb_result)

    # SVM
    svm_model, svm_train_acc, svm_test_acc = train_svm(x_train_n, y_train, x_test_n, y_test, args.seed, args.svm_c)
    svm_path = artifacts_dir / f"{args.prefix}_svm.joblib"
    try:
        import joblib
        joblib.dump(svm_model, svm_path)
    except Exception:
        pass
    svm_result = BenchmarkResult(
        model_name="SVM (RBF)",
        train_accuracy=svm_train_acc,
        test_accuracy=svm_test_acc,
        artifact_size_bytes=estimate_model_size_bytes(svm_model, svm_path),
        avg_inference_ms=measure_latency(svm_model, x_test_n),
        note=f"C={args.svm_c}; support_vectors={len(getattr(svm_model, 'support_', []))}",
    )
    results.append(svm_result)

    csv_path = artifacts_dir / f"{args.prefix}_results.csv"
    json_path = artifacts_dir / f"{args.prefix}_results.json"
    plot_accuracy_path = artifacts_dir / f"{args.prefix}_accuracy.png"
    plot_size_path = artifacts_dir / f"{args.prefix}_artifact_size.png"
    plot_latency_path = artifacts_dir / f"{args.prefix}_latency.png"
    plot_esp32_score_path = artifacts_dir / f"{args.prefix}_esp32_score.png"

    esp32_scores = calculate_esp32_scores(results)
    best_for_esp32 = max(results, key=lambda r: esp32_scores.get(r.model_name, 0.0))

    write_csv(csv_path, results)
    json_path.write_text(
        json.dumps(
            {
                "results": [r.__dict__ for r in results],
                "best_model": pick_best_model(results).__dict__,
                "esp32_scores": esp32_scores,
                "best_model_for_esp32": {
                    "model_name": best_for_esp32.model_name,
                    "esp32_score": esp32_scores.get(best_for_esp32.model_name, 0.0),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    plot_results(results, plot_accuracy_path, plot_size_path, plot_latency_path, plot_esp32_score_path)

    best = pick_best_model(results)

    print("[benchmark] Results:")
    for r in results:
        esp32_score = esp32_scores.get(r.model_name, 0.0)
        print(
            f"- {r.model_name}: test_acc={r.test_accuracy:.4f}, train_acc={r.train_accuracy:.4f}, "
            f"size={r.artifact_size_bytes} bytes, latency={r.avg_inference_ms:.4f} ms/sample, esp32_score={esp32_score:.2f}"
        )
    print(f"[benchmark] Best model: {best.model_name}")
    print(f"[benchmark] Best model for ESP32: {best_for_esp32.model_name} ({esp32_scores.get(best_for_esp32.model_name, 0.0):.2f}/100)")
    print(f"[benchmark] CSV: {csv_path.name}")
    print(f"[benchmark] JSON: {json_path.name}")
    print(f"[benchmark] Plot (accuracy): {plot_accuracy_path.name}")
    print(f"[benchmark] Plot (artifact size): {plot_size_path.name}")
    print(f"[benchmark] Plot (latency): {plot_latency_path.name}")
    print(f"[benchmark] Plot (esp32 score): {plot_esp32_score_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
