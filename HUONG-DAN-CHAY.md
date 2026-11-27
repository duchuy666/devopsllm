# Hướng dẫn cài đặt và chạy hệ thống

Hệ thống hỗ trợ phát hiện và chẩn đoán sự cố DevOps sử dụng LLM kết hợp RAG. Mọi lệnh chạy từ thư mục gốc của dự án.

## 1. Yêu cầu

| Thành phần | Phiên bản đã kiểm chứng |
|---|---|
| Máy | Apple Silicon (ARM64), RAM 16 GB, trống ≥ 30 GB đĩa |
| Docker Desktop | 4 CPU, 8 GB RAM cho VM |
| Minikube / kubectl / Helm | Kubernetes v1.37.0 (ghim trong `config/testbed.env`) |
| Python | 3.12 |
| Gemini API key | Chỉ cần cho chẩn đoán B1–B3 và lập chỉ mục RAG |

```bash
brew install minikube kubectl helm python@3.12
brew install --cask docker-desktop
open -a Docker
```

## 2. Cài môi trường Python và khóa API

```bash
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install -r requirements-assistant.lock -r requirements-testbed.txt
cp .env.example .env
```

Mở `.env`, điền `GEMINI_API_KEY`. Không đưa file `.env` lên Git.

Kiểm tra nhanh, không cần cluster:

```bash
make doctor
make test
```

`make test` chạy 125 unit test (xử lý dữ liệu, context, chấm điểm, quy trình duyệt).

## 3. Dựng testbed (lần đầu, khoảng 30–45 phút)

```bash
make cluster-start            # Minikube profile shyn-thesis, 4 CPU, 7 GiB
make chaos-install            # Chaos Mesh 2.8.8
make sock-shop-deploy         # ứng dụng mẫu Sock Shop
make observability-deploy     # Prometheus, Alertmanager, Loki + Alloy, Jaeger, Grafana
make collector-deploy         # incident collector (FastAPI) nhận webhook Alertmanager
make qdrant-start             # Qdrant trong Docker
```

Ba dịch vụ Go (payment, catalogue, user) chạy bản build ARM64 gốc, cần build một lần (chi tiết: `docs/runbooks/RB-10-native-go.md`):

```bash
.venv/bin/python scripts/prepare_native_sources.py
for s in payment catalogue user; do .venv/bin/python scripts/build_native_go.py $s; done
for s in payment catalogue user; do bash -c "source scripts/common.sh; .venv/bin/python scripts/package_native_go.py $s"; done
bash -c 'source scripts/common.sh; .venv/bin/python scripts/deploy_native_go.py'
```

Lập chỉ mục tri thức cho RAG (5 runbook trong `knowledge/runbooks/`, có gọi API embedding):

```bash
make rag-index
```

## 4. Chạy hằng ngày

```bash
make cluster-start
make qdrant-start
```

Mỗi lệnh sau giữ trong một terminal riêng:

```bash
make sock-shop-forward     # Sock Shop  http://127.0.0.1:8080
make monitoring-forward    # Grafana :3000, Prometheus :9090, Loki :3100, Jaeger :16686
make collector-forward     # Collector  http://127.0.0.1:8000
make ui                    # Giao diện  http://127.0.0.1:8501
```

Kiểm tra sức khỏe:

```bash
make smoke             # 2 lượt mua hàng qua Sock Shop
make telemetry-check   # có đủ log, metric, trace
make gemini-probe      # khóa API hợp lệ (1 lượt gọi)
```

## 5. Demo luồng cảnh báo → chẩn đoán tự động

Terminal 1: bật worker tự chẩn đoán, giới hạn số lượt gọi Gemini:

```bash
bash -c 'source scripts/common.sh; .venv/bin/python scripts/auto_diagnose.py --max-calls 1 --match alertname=SockShopCPUHigh'
```

Terminal 2: tiêm lỗi CPU vào payment (tự hết sau 120 giây):

```bash
kubectl --kubeconfig .runtime/kubeconfig apply -f infra/chaos-mesh/demo/live-ttd-cpu-payment.yaml
```

Luồng diễn ra: Prometheus phát hiện CPU cao → Alertmanager gửi webhook → collector thu telemetry trong cửa sổ ±30 giây → Context Builder (Drain3, chọn metric/trace, mã bằng chứng) → truy xuất runbook từ Qdrant → Gemini sinh báo cáo. Kết quả ở `results/live-diagnoses/<incident>/ttd.json` và tab chẩn đoán trên giao diện. Thời gian đo được từ cảnh báo đến báo cáo: khoảng 40 giây.

Các lỗi demo khác: `live-ttd-cpu-shipping.yaml`, `live-ttd-cpu-catalogue.yaml`. Dọn lỗi sớm:

```bash
kubectl --kubeconfig .runtime/kubeconfig delete -f infra/chaos-mesh/demo/live-ttd-cpu-payment.yaml
```

## 6. Thu dữ liệu và đánh giá (tùy chọn)

| Việc | Lệnh | Tài liệu |
|---|---|---|
| Kế hoạch 200 kịch bản | `make dataset-plan` | `docs/collection-protocol.md` |
| Kiểm tra ổn định 10 phút | `make stability` | `docs/runbooks/RB-09-scenario-runner.md` |
| Thu dữ liệu theo release | `scripts/run_dataset_collection.py --release ... --execute` | `docs/runbooks/RB-15-prospective-collection.md` |
| Duyệt ca | tab Review dữ liệu trên giao diện, sau đó `make admission-preview`, `make admission-apply` | `docs/runbooks/RB-15-prospective-collection.md` |
| Benchmark B0–B3 | `scripts/run_early_benchmark.py --journal ...` | `docs/runbooks/RB-07-benchmark.md`, `docs/benchmark-rubric.md` |

B0 là luật (không gọi API); B1–B3 gọi Gemini và mặc định chỉ chạy ở chế độ xem trước, cần `--execute` mới gọi API.

## 7. Dừng

Ctrl+C ở các terminal port-forward và giao diện, sau đó:

```bash
make cluster-stop
```

Dữ liệu cluster được giữ lại. Xử lý sự cố và khôi phục: `docs/runbooks/RB-08-demo-recovery.md`. Danh mục runbook: `docs/runbooks/README.md`.

## 8. Cấu trúc thư mục

| Thư mục | Nội dung |
|---|---|
| `app/` | Collector, Context Builder, RAG, chẩn đoán, schema báo cáo |
| `ui/` | Giao diện Streamlit |
| `scripts/` | Dựng testbed, thu dữ liệu, duyệt, benchmark |
| `experiments/` | Kế hoạch kịch bản, chấm điểm, kiểm tra cấu trúc ca |
| `infra/` | Manifest Kubernetes, Chaos Mesh, observability, build Go |
| `knowledge/` | Runbook tri thức cho RAG |
| `config/` | Cấu hình testbed và giao thức thu dữ liệu |
| `tests/` | Unit test |
| `docs/` | Giao thức, quyết định thiết kế, runbook vận hành |
