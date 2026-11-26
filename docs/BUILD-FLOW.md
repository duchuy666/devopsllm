# Luồng build đến sản phẩm và thực nghiệm khóa luận

Cập nhật 23/11/2026. Giữ kiến trúc và ba nhóm lỗi trong kế hoạch; Gemini thay OpenAI theo yêu cầu. Báo cáo Word gốc không bị sửa.

| Bước | Làm gì | Chuẩn bị | Điều kiện qua bước |
|---|---|---|---|
| 1 | Ghim môi trường/testbed | Máy cắm nguồn, Docker 8GB, Minikube 7GiB/4 CPU, image/chart lock | Node Ready, rollout, checkout; công bố giả lập |
| 2 | Xác minh telemetry | Port-forward, traffic giả, scrape/log labels, Zipkin | Metric/log/trace liên service, query/time window được lưu |
| 3 | Thu pilot 5 biến thể | RB04, Chaos Mesh khỏe, không lỗi chồng, baseline | Tác động đúng target, cleanup/recovery; lưu cả ca lỗi |
| 4 | Chuẩn hóa observation | Drain3/redact, container ID filter, evidence index | Không lẫn ground truth; cờ thiếu dữ liệu và context version |
| 5 | RAG/Gemini/UI | Key .env, Qdrant, 5 runbook review, payload được duyệt | Report thật, schema/evidence ID, token/latency/ledger; đã lưu19report development |
| 6 | Ổn định/chuẩn bị dataset | Soak, CPU/RAM budget, scenario plan, generalized runner | Không restart nền trong kiểm tra đã định; admission/near-duplicate review |
| 7 | Thu reference/validation | Plan 120/40/40 chia nhóm; cửa sổ/cutoff nhất quán | Tác động + telemetry + recovery có bằng chứng; calibrate rồi freeze |
| 8 | Benchmark test | 40 test ngoài KB, model/KB/prompt/rules frozen, ngân sách API | B0–B3 cùng case; giữ API failure/missing report trong thống kê |
| 9 | Review/đo người thật | Rubric, người chấm độc lập, phiên đo không lộ đáp án | Grounding/hallucination/thời gian có số đo |
| 10 | Hồ sơ tái lập/báo cáo | Hash, versions, export, kết quả và sai số | Chạy lại demo, phân tích giới hạn, kết luận từ dữ liệu thật |

## Lệnh hiện có

```bash
make cluster-start
make qdrant-start
```

Mỗi lệnh sau chạy trong terminal riêng từ root dự án, giữ tiến trình mở:

```bash
make sock-shop-forward
make monitoring-forward
make collector-forward
make ui
```

Trước pilot, kiểm tra:

```bash
make smoke
make telemetry-check
bash -c 'source scripts/common.sh; caffeinate -di .venv/bin/python scripts/check_stability.py --seconds 600'
```

Soak10phút với gateUTC là sàng lọc ngắn, không thay kiểm tra dài hạn. Không chạy soak và chaos/batch cùng lúc. Bằng chứng Ready/restart/UID của ứng dụng và monitoring/chaos, cgroup OOM/PSI, node pressure, traffic, manifest hash lưu ở `results/stability/`; có lỗi thì dừng nghiệm thu.

`make dataset-plan` chỉ lập kế hoạch 200 dòng. `scripts/run_pilot.py` giữ pilot target cố định. Runner mới `scripts/run_scenario.py` dựng được 200 manifest, có preflight/shared lock/receipt/ownership cleanup. Sau native migration và soak mới, đã kiểm chứng tác động qua runner cho CPU, memory, delay, loss và Pod failure ở mức development calibration; chưa admission chính thức. Xem [kết quả calibration](progress/REFERENCE-CALIBRATION.md) và RB09; không dùng render để bulk-apply.

## Diễn giải kết quả

Một report CPU đúng chưa chứng minh accuracy. Snapshot captured chưa là diagnosis. Memory pressure chưa là OOM. Loss 20% không đồng nghĩa 20% HTTP lỗi. Replay latency chưa là live TTD. Giá generation tham chiếu chưa là hóa đơn hoặc ROI. Các tiêu chí này giúp kết quả khóa luận kiểm tra lại được.
