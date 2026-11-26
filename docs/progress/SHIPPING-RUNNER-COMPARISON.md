# Shipping: kiểm tra runner và so sánh B1–B3

Cập nhật ngày 22/11/2026, giờ Việt Nam. Timestamp trong artifact dùng UTC. Đây là một ca reference development calibration; chưa được admission vào dataset chính thức.

## Bằng chứng chạy thực tế

- Soak 600 giây đạt **327 checkout, 0 request lỗi**; có 21 mẫu. Working set bằng 83,8–88,5% cap node, PSI full avg10 tối đa 0,01%, node-local OOM kill không tăng.
- S0011 tiêm hai CPU worker ở load 100% vào `shipping` trong 90 giây. Container record của controller khớp đúng Pod/container dự kiến.
- CPU baseline mean **0,00594 core**, fault peak **0,99898 core**, limit **1 core**. Ba mẫu CPU cuối có mean 0,00788 core. CPU dùng rate 1 phút nên recovery mean có đuôi giảm dần.
- Cleanup/recovery đạt; **118 checkout, 0 request lỗi**. Không đổi lifecycle ngoài target hoặc tăng node-local OOM theo snapshot/counter.
- Export **7.623 dòng log, 236 trace**, không có cờ incomplete hoặc chạm trace cap; có trace liên service.
- Context v0.3 `CTX-f7afb08ddfe940b4` giữ 35 metric, 15 log template, 15 span, không thiếu nguồn.
- Collector nhận đúng `SockShopCPUHigh` của shipping, sau inject-confirmed 81,65 giây. Context sẵn sàng sau alert-received khoảng 30,58 giây. Đây chưa là live LLM TTD.

## Gemini theo gói đã duyệt

| Cấu hình | Top-1 | Đúng target/class | Input/output token | Replay (giây) | Estimate USD |
|---|---|---|---:|---:|---:|
| B1 | queue-master / Pod Failure | Không | 3974/328 | 4.81 | 0.00421050 |
| B2 | queue-master / Pod Failure | Không | 5470/348 | 6.29 | 0.00540750 |
| B3 | shipping / Resource Exhaustion | Có | 13835/468 | 6.55 | 0.01213125 |

Tổng **23,279 input + 1,144 output token**. Generation estimate **0.02174925 USD** theo bảng giá đã lưu; chưa gồm embedding/index và chưa đối chiếu hóa đơn. Có hai query embedding mới; SDK không trả usage nên chưa tính token/chi phí của chúng. Không retry hoặc reindex.

B3 trích E-M001 (CPU), E-M034 (limit 1 core) và E-T007 (`orders → shipping`, 135 ms). Bằng chứng hỗ trợ CPU gần limit; chưa trực tiếp chứng minh throttling hoặc CPU gây latency. Report cũng yêu cầu thêm throttling metrics. Giả thuyết phụ queue-master vẫn cần review.

B1/B2 chọn queue-master từ lỗi socket Docker có thật trong baseline. Kết quả sai so với sự cố CPU được tiêm; phân loại Pod Failure thiếu bằng chứng lifecycle. Không gọi toàn bộ log/rationale đó là dữ kiện bịa. Hai ví dụ này có nhiễu/lỗi nền đã biết, không phải môi trường hoàn toàn sạch lỗi.

Confidence B1/B2/B3 là 0,95/0,85/0,88, chưa hiệu chỉnh. Hai câu trả lời chọn sai vẫn có confidence cao. Root cause của B3 dùng tiếng Anh dù yêu cầu giải thích tiếng Việt; output gốc được giữ nguyên.

## Giới hạn diễn giải

Trên hai ví dụ CPU (payment cũ và shipping mới), B1/B2 mỗi mode chọn sai target ở 2/2 ca; B3 đúng ở 2/2 ca. Đây chỉ là đếm mô tả: cùng nhóm CPU, khác environment/context version, chưa phải test accuracy hoặc bằng chứng lợi ích RAG có ý nghĩa thống kê.

Context v0.3 giữ các limit liên quan tốt hơn v0.2 trong kiểm tra local. Chưa có thí nghiệm cùng case/model chỉ thay selection policy để quy thay đổi chẩn đoán cho policy.

Structural/effect review là assistant technical review. Independent human review, near-duplicate/protocol freeze và official admission còn pending. Ground truth/evaluation manifest không được gửi model hoặc index Qdrant. Official admitted vẫn **0/200**.

## Artifact

- Candidate: `data/candidates/CANDIDATE-20261121T233425132808-S0011/`, gồm quality/effect review, detector evidence và raw telemetry.
- Report/context: `results/diagnoses/CTX-f7afb08ddfe940b4/B1/`, `B2/`, `B3/`.
- Summary: `results/evaluation/shipping-comparison-summary.json`.
- Hai ví dụ: `results/evaluation/development-comparison-B1-B2-B3.json`.
- Approval/execution: `results/approval/gemini-shipping-comparison-20261122/`; ba generation đã dùng hết phạm vi được duyệt.

Chấm lại offline, không gọi API:

```bash
.venv/bin/python experiments/evaluate.py experiments/shipping-comparison-evaluation.json --output results/evaluation/shipping-comparison-B1-B2-B3.json
```
