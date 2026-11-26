# RB 18 — Đáp ứng đề cương: case memory, live TTD, Grafana, nhãn dataset

Bổ sung ngày 25/11/2026 để project khớp báo cáo sơ bộ. Không sửa file nào release v3 ghim hash, nên đợt thu đang chạy không bị ảnh hưởng; kiểm tra bằng `verify_release` cho cả ba split.

| Yêu cầu đề cương | Thành phần | Trạng thái |
|---|---|---|
| RAG từ runbook **và case lịch sử** (§3.1, §5.4) | `app/case_memory.py`, `app/diagnosis_cases.py`, `scripts/index_case_memory.py` | Code xong; chờ ca reference được admitted |
| TTD = alert → incident report (§4 bước 9, §6.2) | `scripts/auto_diagnose.py` → `results/live-diagnoses/<incident>/ttd.json` | Code xong; chưa chạy (tốn API) |
| Grafana dashboard (§3) | `scripts/build_grafana_dashboard.py`, `scripts/deploy_grafana_dashboard.sh` | Đã sinh overlay; chưa deploy |
| Trường `expected_evidence`, `runbook_id` (§5.3) | `scripts/export_dataset_labels.py` → `results/dataset-labels/labels.json` | Chạy được; đầy dần khi reviewer duyệt |

## Case memory

Chỉ ca **admitted** thuộc split **reference** mới được index; validation/test bị từ chối trong code. Tài liệu mỗi ca gồm triệu chứng từ cùng cửa sổ quan sát của mô hình và nhãn đã review; không chứa tham số chaos hoặc qdisc. Collection Qdrant tách khỏi runbook.

```bash
make case-memory-preview
.venv/bin/python scripts/index_case_memory.py --execute
```

`--execute` gọi một embedding Gemini cho mỗi ca. Index sau khi review xong reference và **trước** khi sinh report validation/test; không index lại sau khi đã chạy test. B2/B3 có case memory lưu ở `results/diagnoses/<ctx>/B3-cases/`, runbook hit vẫn ở `knowledge`, case hit ở `retrieved_cases`. Đưa case memory vào cấu hình benchmark chính thức là thay đổi cấu hình B2/B3: phải ghi vào protocol và freeze trước khi mở test.

## Live TTD

```bash
bash -c 'source scripts/common.sh; .venv/bin/python scripts/auto_diagnose.py --max-calls 5'
```

Bắt buộc `--max-calls` (1–50). Chỉ xử lý incident xuất hiện sau khi worker khởi động, và tự tạm dừng khi controller thu dataset đang giữ lock, nên alert của scenario không bị chẩn đoán live. TTD tính từ lúc collector nhận alert tới khi có report, gồm cả thời gian chờ cửa sổ sau alert; báo cáo tách khỏi replay latency. Lượt lỗi vẫn được ghi.

## Grafana

```bash
make grafana-dashboard
```

Dashboard `sockshop-incident` dùng cùng PromQL với collector, cùng log Loki `{namespace="sock-shop"}` và link Jaeger. Script từ chối chạy khi controller đang thu, vì restart Pod Grafana giữa scenario làm lệch kiểm tra lifecycle. Mở bằng `kubectl --context shyn-thesis -n monitoring port-forward svc/grafana 3000:80`.

## Nhãn dataset

```bash
make dataset-labels
```

Chỉ xuất ca admitted. `runbook_id` chỉ có khi reviewer tích "đã chấm relevance"; `expected_evidence` lấy từ vị trí bằng chứng reviewer ghi. Không sửa ground truth gốc; file này không được index hoặc gửi cho mô hình.

## Khóa luận

`make thesis` sinh `docs/submission/khoa_luan_final.docx`; mục live TTD tự điền khi có `results/live-diagnoses/*/ttd.json`.
