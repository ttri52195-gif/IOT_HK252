#!/usr/bin/env python3
"""Comprehensive AI Model Evaluation Script

Evaluates various machine learning models on the train_ready.csv dataset.
Generates detailed performance reports with multiple metrics and visualizations.

Supported Models:
- Gaussian Naive Bayes
- Random Forest
- Support Vector Machine (SVM)
- MLP (shared architecture from benchmark_models.py)

Metrics:
- Accuracy, Precision, Recall, F1-Score
- Confusion Matrix
- Cross-validation scores
- ROC-AUC for binary/multi-class
- Model training time
- Feature importance (where applicable)

Usage:
  python evaluate_models_comprehensive.py --input train_ready.csv
  python evaluate_models_comprehensive.py --input train_ready.csv --test-size 0.2 --output results.json
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import pickle
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import (
    cross_val_score,
    train_test_split,
)
from sklearn.naive_bayes import GaussianNB
from sklearn.preprocessing import LabelEncoder
from sklearn.svm import SVC
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    classification_report,
    ConfusionMatrixDisplay,
)

from benchmark_models import build_mlp

try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

SCRIPT_DIR = Path(__file__).resolve().parent


@dataclass
class EvaluationMetrics:
    """Container for model evaluation metrics."""
    model_name: str
    train_accuracy: float
    test_accuracy: float
    precision_weighted: float
    recall_weighted: float
    f1_weighted: float
    training_time_ms: float
    prediction_time_ms: float
    cv_mean_score: float
    cv_std_score: float
    model_size_kb: float
    esp32_score: float = 0.0
    roc_auc: float | None = None
    note: str = ""

    def to_dict(self):
        data = asdict(self)
        normalized = {}
        for key, value in data.items():
            if isinstance(value, (np.floating, np.integer)):
                normalized[key] = value.item()
            else:
                normalized[key] = value
        return normalized


@dataclass
class Dataset:
    """Container for dataset."""
    X_train: np.ndarray
    X_test: np.ndarray
    y_train: np.ndarray
    y_test: np.ndarray
    label_encoder: LabelEncoder
    unique_labels: List[str]
    feature_names: List[str]


class KerasMLPClassifier:
    """Sklearn-like wrapper for the shared benchmark MLP model."""

    def __init__(self, num_classes: int, epochs: int = 25, batch_size: int = 32, seed: int = 42):
        self.num_classes = num_classes
        self.epochs = epochs
        self.batch_size = batch_size
        self.seed = seed
        self.model = None
        self._mean = None
        self._std = None
        self._model_size_kb = 0.0

    def get_params(self, deep: bool = True):
        return {
            "num_classes": self.num_classes,
            "epochs": self.epochs,
            "batch_size": self.batch_size,
            "seed": self.seed,
        }

    def set_params(self, **params):
        for key, value in params.items():
            setattr(self, key, value)
        return self

    def _normalize(self, x: np.ndarray) -> np.ndarray:
        return ((x - self._mean) / self._std).astype(np.float32)

    def fit(self, x: np.ndarray, y: np.ndarray):
        import tensorflow as tf

        tf.keras.utils.set_random_seed(self.seed)
        self._mean = x.mean(axis=0)
        self._std = np.where(x.std(axis=0) < 1e-6, 1.0, x.std(axis=0))

        x_n = self._normalize(x)
        self.model = build_mlp(self.num_classes)
        self.model.fit(
            x_n,
            y,
            validation_split=0.2,
            epochs=self.epochs,
            batch_size=self.batch_size,
            verbose=0,
        )

        def representative_dataset():
            for i in range(min(len(x_n), 300)):
                yield [x_n[i : i + 1].astype(np.float32)]

        # Estimate deployment artifact size using INT8 TFLite.
        with tempfile.TemporaryDirectory() as tmpdir:
            tflite_path = Path(tmpdir) / "eval_mlp_int8.tflite"
            converter = tf.lite.TFLiteConverter.from_keras_model(self.model)
            converter.optimizations = [tf.lite.Optimize.DEFAULT]
            converter.representative_dataset = representative_dataset
            converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
            converter.inference_input_type = tf.int8
            converter.inference_output_type = tf.int8
            tflite_path.write_bytes(converter.convert())
            self._model_size_kb = tflite_path.stat().st_size / 1024.0

        return self

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Model is not trained yet")
        return self.model.predict(self._normalize(x), verbose=0)

    def predict(self, x: np.ndarray) -> np.ndarray:
        proba = self.predict_proba(x)
        return np.argmax(proba, axis=1)

    @property
    def model_size_kb(self) -> float:
        return self._model_size_kb


class ModelEvaluator:
    """Comprehensive model evaluator for classification tasks."""

    def __init__(self, test_size: float = 0.2, random_state: int = 42, cv_folds: int = 5):
        self.test_size = test_size
        self.random_state = random_state
        self.cv_folds = cv_folds
        self.results: List[EvaluationMetrics] = []

    def load_dataset(self, csv_path: Path) -> Dataset:
        """Load and preprocess dataset from CSV."""
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

        X = np.column_stack([temperatures, humidities])
        le = LabelEncoder()
        y = le.fit_transform(raw_labels)

        # Split dataset
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=self.test_size, random_state=self.random_state, stratify=y
        )

        dataset = Dataset(
            X_train=X_train,
            X_test=X_test,
            y_train=y_train,
            y_test=y_test,
            label_encoder=le,
            unique_labels=list(le.classes_),
            feature_names=["temperature", "humidity"],
        )

        print(f"✓ Dataset loaded: {len(X)} samples")
        print(f"  - Training set: {len(X_train)} samples")
        print(f"  - Test set: {len(X_test)} samples")
        print(f"  - Classes: {len(le.classes_)} ({', '.join(le.classes_)})")
        print()

        return dataset

    def evaluate_model(
        self,
        name: str,
        model,
        dataset: Dataset,
        feature_importance: bool = False,
    ) -> EvaluationMetrics:
        """Evaluate a single model."""
        print(f"Evaluating {name}...")

        # Training time
        start = time.perf_counter()
        model.fit(dataset.X_train, dataset.y_train)
        train_time_ms = (time.perf_counter() - start) * 1000

        # Predictions
        start = time.perf_counter()
        y_pred_train = model.predict(dataset.X_train)
        y_pred_test = model.predict(dataset.X_test)
        pred_time_ms = (time.perf_counter() - start) * 1000

        # Accuracy
        train_acc = accuracy_score(dataset.y_train, y_pred_train)
        test_acc = accuracy_score(dataset.y_test, y_pred_test)

        # Weighted metrics
        precision = precision_score(dataset.y_test, y_pred_test, average="weighted", zero_division=0)
        recall = recall_score(dataset.y_test, y_pred_test, average="weighted", zero_division=0)
        f1 = f1_score(dataset.y_test, y_pred_test, average="weighted", zero_division=0)

        # Cross-validation
        try:
            cv_scores = cross_val_score(model, dataset.X_train, dataset.y_train, cv=self.cv_folds)
        except Exception:
            cv_scores = np.array([test_acc], dtype=np.float32)

        # Model size
        model_size_kb = self._calculate_model_size(model)

        # ROC-AUC (only for binary or use ovr/ovo for multiclass)
        roc_auc = None
        if len(dataset.unique_labels) == 2:
            try:
                y_proba = model.predict_proba(dataset.X_test)[:, 1]
                roc_auc = roc_auc_score(dataset.y_test, y_proba)
            except (AttributeError, ValueError):
                roc_auc = None
        elif len(dataset.unique_labels) > 2:
            try:
                y_proba = model.predict_proba(dataset.X_test)
                roc_auc = roc_auc_score(
                    dataset.y_test, y_proba, multi_class="ovr"
                )
            except (AttributeError, ValueError):
                roc_auc = None

        # Feature importance
        note = ""
        if feature_importance and hasattr(model, "feature_importances_"):
            importances = model.feature_importances_
            note = f"Feature importance: {', '.join(f'{name}: {imp:.3f}' for name, imp in zip(dataset.feature_names, importances))}"

        metrics = EvaluationMetrics(
            model_name=name,
            train_accuracy=train_acc,
            test_accuracy=test_acc,
            precision_weighted=precision,
            recall_weighted=recall,
            f1_weighted=f1,
            training_time_ms=train_time_ms,
            prediction_time_ms=pred_time_ms,
            cv_mean_score=cv_scores.mean(),
            cv_std_score=cv_scores.std(),
            model_size_kb=model_size_kb,
            roc_auc=roc_auc,
            note=note,
        )

        self.results.append(metrics)
        self._print_metrics(metrics, dataset.y_test, y_pred_test, dataset.unique_labels)

        return metrics

    def _print_metrics(self, metrics: EvaluationMetrics, y_test, y_pred, labels: List[str]):
        """Print evaluation metrics."""
        print(f"\n  Train Accuracy: {metrics.train_accuracy:.4f}")
        print(f"  Test Accuracy:  {metrics.test_accuracy:.4f}")
        print(f"  Precision (weighted): {metrics.precision_weighted:.4f}")
        print(f"  Recall (weighted):    {metrics.recall_weighted:.4f}")
        print(f"  F1-Score (weighted):  {metrics.f1_weighted:.4f}")
        print(f"  Cross-validation: {metrics.cv_mean_score:.4f} (+/- {metrics.cv_std_score:.4f})")
        if metrics.roc_auc is not None:
            print(f"  ROC-AUC: {metrics.roc_auc:.4f}")
        print(f"  Training time: {metrics.training_time_ms:.2f} ms")
        print(f"  Prediction time (test set): {metrics.prediction_time_ms:.2f} ms")
        print(f"  Model size: {metrics.model_size_kb:.2f} KB")
        if metrics.note:
            print(f"  {metrics.note}")
        print()

    def _calculate_model_size(self, model) -> float:
        """Calculate model size in KB by serializing with pickle."""
        if hasattr(model, "model_size_kb"):
            return float(model.model_size_kb)

        try:
            buffer = io.BytesIO()
            pickle.dump(model, buffer)
            size_bytes = buffer.tell()
            size_kb = size_bytes / 1024.0
            return size_kb
        except Exception as e:
            print(f"  Warning: Could not calculate model size: {e}")
            return 0.0

    def calculate_esp32_scores(self):
        """Calculate ESP32-specific scores for all models.
        
        Score formula (0-100):
        - Accuracy weight: 40%
        - Size penalty: 30% (smaller is better, 0-1000KB = good, >1MB = bad)
        - Speed bonus: 30% (faster prediction is better)
        """
        if not self.results:
            return

        # Normalize metrics
        accuracies = [m.test_accuracy for m in self.results]
        sizes = [m.model_size_kb for m in self.results]
        pred_times = [m.prediction_time_ms for m in self.results]

        max_acc = max(accuracies) if accuracies else 1.0
        max_size = max(sizes) if sizes else 1.0
        max_time = max(pred_times) if pred_times else 1.0

        for metric in self.results:
            # Accuracy score (0-40)
            acc_score = (metric.test_accuracy / max_acc) * 40

            # Size penalty (0-30): smaller is better
            # Normalize: ideal < 100KB, bad > 1000KB
            size_normalized = min(metric.model_size_kb / 100.0, 10.0)
            size_score = (1.0 - min(size_normalized / 10.0, 1.0)) * 30

            # Speed bonus (0-30): faster is better
            speed_score = (1.0 - (metric.prediction_time_ms / max_time)) * 30

            # Total score
            esp32_score = acc_score + size_score + speed_score
            metric.esp32_score = esp32_score

    def run_evaluation(self, dataset_path: Path) -> List[EvaluationMetrics]:
        """Run evaluation on all models."""
        dataset = self.load_dataset(dataset_path)

        # Define models
        models = [
            ("Gaussian Naive Bayes", GaussianNB()),
            ("Random Forest", RandomForestClassifier(n_estimators=100, random_state=self.random_state, n_jobs=-1)),
            ("SVM (RBF kernel)", SVC(kernel="rbf", C=1.0, probability=True, random_state=self.random_state)),
            ("MLP (Shared from benchmark)", KerasMLPClassifier(num_classes=len(dataset.unique_labels), seed=self.random_state)),
        ]

        print("=" * 70)
        print("COMPREHENSIVE MODEL EVALUATION")
        print("=" * 70)
        print()

        for name, model in models:
            self.evaluate_model(
                name, 
                model, 
                dataset,
                feature_importance=name in ["Random Forest"]
            )

        # Calculate ESP32 scores
        self.calculate_esp32_scores()

        return self.results

    def generate_summary(self) -> Dict:
        """Generate summary statistics."""
        if not self.results:
            return {}

        best_by_accuracy = max(self.results, key=lambda x: x.test_accuracy)
        best_by_f1 = max(self.results, key=lambda x: x.f1_weighted)
        best_by_speed = min(self.results, key=lambda x: x.training_time_ms)
        best_for_esp32 = max(self.results, key=lambda x: x.esp32_score)

        summary = {
            "total_models_evaluated": len(self.results),
            "best_model_accuracy": {
                "name": best_by_accuracy.model_name,
                "test_accuracy": best_by_accuracy.test_accuracy,
                "f1_score": best_by_accuracy.f1_weighted,
            },
            "best_model_f1_score": {
                "name": best_by_f1.model_name,
                "f1_score": best_by_f1.f1_weighted,
                "test_accuracy": best_by_f1.test_accuracy,
            },
            "fastest_model": {
                "name": best_by_speed.model_name,
                "training_time_ms": best_by_speed.training_time_ms,
            },
            "best_for_esp32": {
                "name": best_for_esp32.model_name,
                "esp32_score": best_for_esp32.esp32_score,
                "test_accuracy": best_for_esp32.test_accuracy,
                "model_size_kb": best_for_esp32.model_size_kb,
                "prediction_time_ms": best_for_esp32.prediction_time_ms,
            },
            "average_test_accuracy": np.mean([m.test_accuracy for m in self.results]),
            "average_f1_score": np.mean([m.f1_weighted for m in self.results]),
            "average_model_size_kb": np.mean([m.model_size_kb for m in self.results]),
        }

        return summary

    def export_results(self, output_path: Path | str):
        """Export results to JSON."""
        output_path = Path(output_path)
        
        results_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "models": [m.to_dict() for m in self.results],
            "summary": self.generate_summary(),
        }

        with output_path.open("w", encoding="utf-8") as f:
            json.dump(results_data, f, indent=2, ensure_ascii=False)

        print(f"✓ Results exported to {output_path}")

    def print_summary(self):
        """Print summary report."""
        summary = self.generate_summary()
        
        print("\n" + "=" * 70)
        print("SUMMARY REPORT")
        print("=" * 70)
        print(f"\nTotal models evaluated: {summary['total_models_evaluated']}")
        print(f"\nBest Model (by Accuracy):")
        print(f"  Model: {summary['best_model_accuracy']['name']}")
        print(f"  Accuracy: {summary['best_model_accuracy']['test_accuracy']:.4f}")
        print(f"  F1-Score: {summary['best_model_accuracy']['f1_score']:.4f}")
        
        print(f"\nBest Model (by F1-Score):")
        print(f"  Model: {summary['best_model_f1_score']['name']}")
        print(f"  F1-Score: {summary['best_model_f1_score']['f1_score']:.4f}")
        print(f"  Accuracy: {summary['best_model_f1_score']['test_accuracy']:.4f}")
        
        print(f"\nFastest Model:")
        print(f"  Model: {summary['fastest_model']['name']}")
        print(f"  Training Time: {summary['fastest_model']['training_time_ms']:.2f} ms")
        
        print(f"\nBest Model for ESP32:")
        print(f"  Model: {summary['best_for_esp32']['name']}")
        print(f"  ESP32 Score: {summary['best_for_esp32']['esp32_score']:.2f}/100")
        print(f"  Accuracy: {summary['best_for_esp32']['test_accuracy']:.4f}")
        print(f"  Model Size: {summary['best_for_esp32']['model_size_kb']:.2f} KB")
        print(f"  Prediction Time: {summary['best_for_esp32']['prediction_time_ms']:.2f} ms")
        
        print(f"\nOverall Performance:")
        print(f"  Average Accuracy: {summary['average_test_accuracy']:.4f}")
        print(f"  Average F1-Score: {summary['average_f1_score']:.4f}")
        print(f"  Average Model Size: {summary['average_model_size_kb']:.2f} KB")
        print("\n" + "=" * 70)

    def generate_comparison_table(self):
        """Print a comparison table of all models."""
        if not self.results:
            return

        print("\n" + "=" * 140)
        print("MODEL COMPARISON TABLE")
        print("=" * 140)
        print(f"{'Model':<25} {'Train Acc':<12} {'Test Acc':<12} {'Precision':<12} {'Recall':<12} {'F1-Score':<12} {'CV Score':<12}")
        print("-" * 140)
        
        for metric in self.results:
            print(
                f"{metric.model_name:<25} "
                f"{metric.train_accuracy:<12.4f} "
                f"{metric.test_accuracy:<12.4f} "
                f"{metric.precision_weighted:<12.4f} "
                f"{metric.recall_weighted:<12.4f} "
                f"{metric.f1_weighted:<12.4f} "
                f"{metric.cv_mean_score:<12.4f}"
            )
        print("=" * 140)

    def print_esp32_ranking(self):
        """Print ESP32 suitability ranking with detailed metrics."""
        if not self.results:
            return

        # Sort by ESP32 score
        sorted_results = sorted(self.results, key=lambda x: x.esp32_score, reverse=True)

        print("\n" + "=" * 140)
        print("ESP32 SUITABILITY RANKING")
        print("=" * 140)
        print("\nScore Formula:")
        print("  - Accuracy (40%): Higher is better")
        print("  - Model Size (30%): Smaller is better (ideal: <100KB, bad: >1000KB)")
        print("  - Prediction Speed (30%): Faster is better")
        print("\n" + "-" * 140)
        print(f"{'Rank':<6} {'Model':<25} {'ESP32 Score':<15} {'Accuracy':<12} {'Size (KB)':<12} {'Pred Time (ms)':<15} {'Status':<20}")
        print("-" * 140)

        for rank, metric in enumerate(sorted_results, 1):
            # Determine status based on ESP32 score and size
            if metric.model_size_kb > 1000:
                status = "⚠️  Large"
            elif metric.model_size_kb > 500:
                status = "✓ Moderate"
            else:
                status = "✓✓ Ideal"

            print(
                f"{rank:<6} "
                f"{metric.model_name:<25} "
                f"{metric.esp32_score:<15.2f} "
                f"{metric.test_accuracy:<12.4f} "
                f"{metric.model_size_kb:<12.2f} "
                f"{metric.prediction_time_ms:<15.2f} "
                f"{status:<20}"
            )

        print("=" * 140)
        print("\nRECOMMENDATION:")
        best = sorted_results[0]
        print(f"  🏆 Best for ESP32: {best.model_name}")
        print(f"     - ESP32 Score: {best.esp32_score:.2f}/100")
        print(f"     - Test Accuracy: {best.test_accuracy:.4f}")
        print(f"     - Model Size: {best.model_size_kb:.2f} KB")
        print(f"     - Prediction Time: {best.prediction_time_ms:.2f} ms")
        print(f"     - RAM Usage (est.): ~{best.model_size_kb * 2:.0f} KB")
        print("=" * 140)

    def generate_visualizations(self, dataset_path: Path, output_dir: Path | str = None):
        """Generate visualization plots."""
        if not MATPLOTLIB_AVAILABLE:
            print("Warning: matplotlib not available. Skipping visualizations.")
            return

        output_dir = Path(output_dir or SCRIPT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Accuracy comparison
        fig, ax = plt.subplots(figsize=(12, 6))
        models = [m.model_name for m in self.results]
        train_accs = [m.train_accuracy for m in self.results]
        test_accs = [m.test_accuracy for m in self.results]

        x = np.arange(len(models))
        width = 0.35

        ax.bar(x - width/2, train_accs, width, label="Train Accuracy", alpha=0.8)
        ax.bar(x + width/2, test_accs, width, label="Test Accuracy", alpha=0.8)

        ax.set_ylabel("Accuracy", fontsize=12)
        ax.set_title("Model Accuracy Comparison", fontsize=14, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(models, rotation=45, ha="right")
        ax.legend()
        ax.grid(axis="y", alpha=0.3)
        plt.tight_layout()
        plt.savefig(output_dir / "model_accuracy_comparison.png", dpi=300, bbox_inches="tight")
        print(f"✓ Saved visualization: model_accuracy_comparison.png")

        # F1-Score comparison
        fig, ax = plt.subplots(figsize=(10, 6))
        f1_scores = [m.f1_weighted for m in self.results]
        colors = plt.cm.viridis(np.linspace(0, 1, len(models)))

        ax.barh(models, f1_scores, color=colors, alpha=0.8)
        ax.set_xlabel("F1-Score (weighted)", fontsize=12)
        ax.set_title("Model F1-Score Comparison", fontsize=14, fontweight="bold")
        ax.grid(axis="x", alpha=0.3)
        plt.tight_layout()
        plt.savefig(output_dir / "model_f1_comparison.png", dpi=300, bbox_inches="tight")
        print(f"✓ Saved visualization: model_f1_comparison.png")

        # Training time comparison
        fig, ax = plt.subplots(figsize=(10, 6))
        train_times = [m.training_time_ms for m in self.results]
        colors = plt.cm.plasma(np.linspace(0, 1, len(models)))

        ax.bar(models, train_times, color=colors, alpha=0.8)
        ax.set_ylabel("Training Time (ms)", fontsize=12)
        ax.set_title("Model Training Time Comparison", fontsize=14, fontweight="bold")
        ax.set_xticklabels(models, rotation=45, ha="right")
        ax.grid(axis="y", alpha=0.3)
        plt.tight_layout()
        plt.savefig(output_dir / "model_training_time.png", dpi=300, bbox_inches="tight")
        print(f"✓ Saved visualization: model_training_time.png")

        # Model size comparison
        fig, ax = plt.subplots(figsize=(10, 6))
        sizes = [m.model_size_kb for m in self.results]
        colors_size = plt.cm.RdYlGn_r(np.linspace(0.2, 0.8, len(models)))

        bars = ax.bar(models, sizes, color=colors_size, alpha=0.8)
        ax.axhline(y=100, color='g', linestyle='--', label='Ideal (<100KB)', linewidth=2)
        ax.axhline(y=500, color='orange', linestyle='--', label='Moderate (<500KB)', linewidth=2)
        ax.axhline(y=1000, color='r', linestyle='--', label='Large (>1000KB)', linewidth=2)
        ax.set_ylabel("Model Size (KB)", fontsize=12)
        ax.set_title("Model Size Comparison (ESP32 Suitability)", fontsize=14, fontweight="bold")
        ax.set_xticklabels(models, rotation=45, ha="right")
        ax.legend()
        ax.grid(axis="y", alpha=0.3)
        plt.tight_layout()
        plt.savefig(output_dir / "model_size_comparison.png", dpi=300, bbox_inches="tight")
        print(f"✓ Saved visualization: model_size_comparison.png")

        # ESP32 Score comparison
        fig, ax = plt.subplots(figsize=(10, 6))
        esp32_scores = [m.esp32_score for m in self.results]
        colors_esp = plt.cm.RdYlGn(np.linspace(0.3, 0.9, len(models)))

        bars = ax.barh(models, esp32_scores, color=colors_esp, alpha=0.8)
        ax.axvline(x=50, color='r', linestyle='--', label='Poor threshold', linewidth=2)
        ax.axvline(x=75, color='g', linestyle='--', label='Good threshold', linewidth=2)
        ax.set_xlabel("ESP32 Score (0-100)", fontsize=12)
        ax.set_title("Model ESP32 Suitability Score\n(Accuracy 40% + Size Efficiency 30% + Speed 30%)", 
                     fontsize=14, fontweight="bold")
        ax.set_xlim(0, 100)
        ax.legend()
        ax.grid(axis="x", alpha=0.3)
        
        # Add score labels
        for i, (bar, score) in enumerate(zip(bars, esp32_scores)):
            ax.text(score + 1, i, f'{score:.1f}', va='center', fontsize=10, fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(output_dir / "model_esp32_score.png", dpi=300, bbox_inches="tight")
        print(f"✓ Saved visualization: model_esp32_score.png")


def main():
    parser = argparse.ArgumentParser(
        description="Comprehensive AI Model Evaluation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input",
        type=str,
        default="train_ready.csv",
        help="Path to training dataset (default: train_ready.csv)",
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.2,
        help="Test set ratio (default: 0.2)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="evaluation_results.json",
        help="Output JSON file for results (default: evaluation_results.json)",
    )
    parser.add_argument(
        "--cv-folds",
        type=int,
        default=5,
        help="Cross-validation folds (default: 5)",
    )
    parser.add_argument(
        "--visualizations",
        action="store_true",
        help="Generate visualization plots",
    )

    args = parser.parse_args()

    # Resolve paths
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = SCRIPT_DIR / input_path

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = SCRIPT_DIR / output_path

    # Check input file
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        exit(1)

    # Run evaluation
    evaluator = ModelEvaluator(test_size=args.test_size, cv_folds=args.cv_folds)
    results = evaluator.run_evaluation(input_path)

    # Print reports
    evaluator.generate_comparison_table()
    evaluator.print_esp32_ranking()
    evaluator.print_summary()

    # Export results
    evaluator.export_results(output_path)

    # Generate visualizations
    if args.visualizations:
        try:
            evaluator.generate_visualizations(input_path, output_path.parent)
        except Exception as e:
            print(f"Warning: Could not generate visualizations: {e}")


if __name__ == "__main__":
    main()
