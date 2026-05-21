# Báo cáo: Benchmark và So sánh Mô hình (benchmark_models.py)

## 1. Mục tiêu

Script `benchmark_models.py` có nhiệm vụ so sánh hiệu năng của bốn mô hình phân loại để chọn ra mô hình phù hợp nhất cho triển khai trên ESP32. Tiêu chí đánh giá bao gồm độ chính xác (accuracy), kích thước artifact, và tốc độ suy luận, giúp cân bằng giữa hiệu năng và ràng buộc tài nguyên thiết bị nhúng.

## 2. Đầu vào và Đầu ra

### Đầu vào
- **File dữ liệu**: `train_ready.csv` chứa các mẫu dữ liệu đã được gán nhãn (temperature, humidity, label)
- **Các tham số cấu hình**:
  - `--input`: đường dẫn CSV đầu vào (mặc định: train_ready.csv)
  - `--test-ratio`: tỉ lệ chia tập test (mặc định: 0.2)
  - `--seed`: seed ngẫu nhiên để tái lập kết quả (mặc định: 42)
  - `--epochs`: số epoch huấn luyện MLP (mặc định: 25)
  - `--batch-size`: batch size MLP (mặc định: 32)
  - `--forest-trees`: số cây của Random Forest (mặc định: 200)
  - `--forest-max-depth`: độ sâu tối đa RF, 0=không giới hạn (mặc định: 0)
  - `--svm-c`: tham số regularization SVM (mặc định: 10.0)
  - `--prefix`: tiền tố tên file output (mặc định: benchmark)

### Đầu ra
- **benchmark_results.csv**: bảng kết quả so sánh 4 mô hình (accuracy, size, latency)
- **benchmark_results.json**: kết quả chi tiết dạng JSON kèm thông tin best model
- **benchmark_comparison.png**: biểu đồ so sánh 3 trục (accuracy, size, latency)
- **benchmark_*.joblib** hoặc **.h5/.tflite**: các file model của từng mô hình

## 3. Thiết kế và Cấu trúc

### 3.1 Các lớp dữ liệu chính

```python
@dataclass
class Dataset:
    x: np.ndarray      # Ma trận dữ liệu (N x 2)
    y: np.ndarray      # Nhãn (N,)
    labels: List[str]  # Tên các lớp

@dataclass
class BenchmarkResult:
    model_name: str              # Tên mô hình
    train_accuracy: float        # Độ chính xác trên tập train
    test_accuracy: float         # Độ chính xác trên tập test
    artifact_size_bytes: int     # Kích thước file model (bytes)
    avg_inference_ms: float      # Thời gian suy luận trung bình (ms)
    note: str                    # Ghi chú bổ sung
```

### 3.2 Luồng xử lý chính

1. **Nạp dữ liệu** (`load_dataset`):
   - Đọc CSV, lọc bỏ dòng thiếu dữ liệu
   - Gán nhãn theo thứ tự ưu tiên (Không hợp lệ → Standby → AC → Dehumidifier → Sprayer)
   - Chuyển đổi sang numpy array, mã hóa nhãn thành index

2. **Chia train/test** (`split_train_test`):
   - Xáo trộn ngẫu nhiên dữ liệu với seed cố định
   - Chia theo tỉ lệ test_ratio (mặc định 20%)
   - Đảm bảo không rỗng cả hai tập

3. **Chuẩn hóa dữ liệu** (`zscore_fit_transform`):
   - Tính mean và std từ tập train
   - Áp dụng z-score: $(x - \mu) / \sigma$
   - Chuẩn hóa cả train và test dùng thống kê từ train

4. **Huấn luyện từng mô hình**:
   - **MLP**: dựng mạng Keras 2 lớp hidden, huấn luyện, sau đó convert sang TFLite INT8
   - **Random Forest**: dùng scikit-learn với số cây tùy chọn
   - **Naive Bayes**: GaussianNB từ scikit-learn
   - **SVM**: SVC với kernel RBF

5. **Đo độ trễ** (`measure_latency`):
   - Chạy warm-up để cache
   - Đo thời gian trên 128 mẫu test
   - Tính trung bình ms per sample

6. **Chọn best model** (`pick_best_model`):
   - Sắp xếp theo: accuracy giảm, size tăng, latency tăng
   - Lấy mô hình đứng đầu (best accuracy, nếu ngang thì nhỏ hơn)

7. **Xuất kết quả**:
   - Ghi bảng CSV (dễ import Excel)
   - Ghi JSON (chi tiết hơn, tương tích API)
   - Vẽ biểu đồ 3 trục (matplotlib)

## 4. Các Mô hình So sánh

### 4.1 MLP (Multi-Layer Perceptron)
- **Kiến trúc**: Input (2) → Dense(16, relu) → Dense(16, relu) → Output(num_classes, softmax)
- **Huấn luyện**: Adam optimizer, sparse_categorical_crossentropy
- **Output**: TFLite INT8 (tối ưu cho ESP32)
- **Ưu điểm**: Có thể học pattern phức tạp, đã tối ưu hóa để triển khai
- **Nhược điểm**: Thường có accuracy thấp hơn tree-based cho bài toán nhỏ

### 4.2 Random Forest
- **Cấu hình**: mặc định 200 cây, độ sâu unlimited
- **Ưu điểm**: Độ chính xác rất cao, tính toán nhanh
- **Nhược điểm**: Model size lớn (190+ KB), khó triển khai trên ESP32
- **Đặc tính**: Có feature importance

### 4.3 Gaussian Naive Bayes
- **Đặc điểm**: Giả định độc lập giữa features, phân phối Gaussian
- **Ưu điểm**: Cực kỳ nhẹ (~1 KB), suy luận siêu nhanh, dễ export C
- **Nhược điểm**: Accuracy có thể thấp hơn các mô hình khác
- **Lý tưởng cho ESP32**: Đây là lựa chọn chính cho thiết bị nhúng

### 4.4 SVM (Support Vector Machine)
- **Kernel**: RBF
- **Tham số**: C=10.0 (mặc định)
- **Ưu điểm**: Độ chính xác cao, ổn định
- **Nhược điểm**: Model size trung bình (~25 KB), độ trễ cao hơn RF

## 5. Kết quả Thực tế

Dựa trên kết quả hiện tại từ [ml/benchmark_test_results.json](ml/benchmark_test_results.json):

| Mô hình | Train Acc | Test Acc | Size (bytes) | Latency (ms) |
|---------|-----------|----------|--------------|------------|
| MLP (INT8) | 0.5453 | 0.5645 | 3,928 | 0.584 |
| Random Forest | 1.0000 | 0.9946 | 190,769 | 0.193 |
| Naive Bayes | 0.9463 | 0.9462 | 1,023 | 0.0009 |
| SVM (RBF) | 0.9879 | 0.9839 | 25,087 | 0.0217 |

**Kết luận**:
- **Best accuracy**: Random Forest (99.46%)
- **Best for ESP32**: Naive Bayes (size 1 KB, latency <1 ms)
- **Trade-off tối ưu**: Naive Bayes cân bằng giữa chính xác (94.6%) và ràng buộc thiết bị

## 6. Hạn chế và Hướng Cải tiến

### Hạn chế hiện tại
1. Benchmark chỉ đo trên tập test cố định; không có cross-validation đầy đủ
2. Không tính overhead khởi động mô hình (warm-up)
3. Chưa thử các hyperparameter khác (số cây, độ sâu RF, kernel SVM)
4. Không có so sánh chi phí huấn luyện với chi phí deployment

### Hướng cải tiến
1. Thêm cross-validation k-fold để ước tính generalization tốt hơn
2. Tính toán memory usage khi load model trên ESP32
3. Sử dụng Bayesian optimization hoặc grid search để fine-tune hyperparameter
4. Tích hợp kiểm tra latency thực tế trên hardware ESP32 (không chỉ PC)
5. Thêm các mô hình khác: XGBoost, LightGBM, Neural Network nhỏ hơn

## 7. Cách Sử Dụng

```bash
# Chạy benchmark với cấu hình mặc định
python ml/benchmark_models.py --input ml/train_ready.csv --prefix benchmark

# Chạy với tuning hyperparameter MLP
python ml/benchmark_models.py --input ml/train_ready.csv --epochs 50 --batch-size 16 --prefix benchmark_v2

# Chạy với RF nhiều cây hơn
python ml/benchmark_models.py --input ml/train_ready.csv --forest-trees 500 --prefix benchmark_v3
```

## 8. Liên kết với Các Bước Tiếp Theo

1. **Từ benchmark_models.py** → chọn mô hình (Naive Bayes được ưu tiên)
2. **Sang export_naive_bayes.py** → xuất thành file .h để nhúng vào firmware
3. **Sang evaluate_models_comprehensive.py** (tùy chọn) → đánh giá chi tiết hơn nếu cần báo cáo
4. **Cuối cùng** → deploy trên ESP32 qua src/tinyml.cpp

---

**Tác giả**: ML Pipeline  
**Ngày cập nhật**: 2026-04-23
