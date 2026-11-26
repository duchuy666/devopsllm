# So sánh B1–B3 trên CPU pilot

Cập nhật 22/11/2026 (giờ Việt Nam). Người dùng đã chấp thuận gói cụ thể; execution journal ghi hoàn tất cả ba mode, không retry.

Context: `CTX-0043135a9e0a5209`; cùng một CPU pilot payment, context v0.2 và observation cutoff. Đây là một ca development, không phải ba case hoặc bộ test chính thức.

| Cấu hình | Top-1 | Đúng target + class | Top-3 | Input/output token | Replay (s) | Generation estimate (USD) |
|---|---|---|---|---:|---:|---:|
| B1 | queue-master / Pod Failure | Không | Không | 3916/295 | 4.59 | 0.00404325 |
| B2 | queue-master / Pod Failure | Không | Không | 5414/352 | 5.95 | 0.00538050 |
| B3 | payment / Resource Exhaustion | Có | Có | 13860/734 | 8.74 | 0.01314750 |

B1 dùng 15 log template, không RAG. B2 cùng 15 log template và RAG. B3 dùng cùng log, thêm 36 metric và 15 span, cùng KB version. Ba kết quả là output thật đã lưu, không tự tạo hoặc sửa để khớp đáp án.

## Diễn giải và lỗi còn lại

- B1/B2 chọn lỗi socket Docker của queue-master. Log lỗi đó có thật nhưng là nhiễu nền, không phải fault CPU payment đã tiêm; phân loại Pod Failure chưa được chứng minh bằng lifecycle evidence. RAG chưa sửa được chẩn đoán trên ca này.
- B3 chọn đúng payment / Resource Exhaustion Top-1. E-M001 cho CPU initial 0,0086 và max 0,198 core; E-T007 là span gọi paymentauth 859ms. Đây là bằng chứng hỗ trợ giả thuyết, chưa trực tiếp chứng minh throttling hoặc quan hệ nhân quả.
- B3 vẫn có giả thuyết orders Resource Exhaustion và queue-master Pod Failure chưa được xác nhận. CPU tăng ở orders không tự chứng minh cạn CPU.
- B3 nói paymentauth chiếm phần lớn thời gian order; 859ms trên span orders 1972,819ms chỉ khoảng 43,5%. Cần gắn cờ diễn đạt quá mạnh thay vì chấm toàn report grounded chỉ vì evidence ID hợp lệ.
- Context giữ loại cpu_limit nhưng không giữ limit của payment/orders sau cắt budget. Việc model yêu cầu thêm limit/throttling là điểm cần xem xét khi sửa chính sách chọn evidence. Không đổi context/report đã duyệt để chấm lại như cùng lượt.
- Confidence B1/B2/B3 lần lượt 0,92/0,85/0,80, chưa hiệu chỉnh; ca sai vẫn có confidence cao. Không dùng confidence làm điểm đúng.
- Đây là review kỹ thuật sơ bộ, chưa có hai người chấm độc lập/claim-level labels, không phải kết quả grounding chính thức. Không thực thi khuyến nghị mount host Docker socket.

## Token, thời gian và chi phí

Generation tổng: 23190 input + 1381 output token. Tổng estimate theo bảng paid standard đã lưu: **0.02257125 USD**, chưa gồm embedding/index và chưa đối chiếu hóa đơn. Actual API cost vẫn null.

API latency B1/B2/B3 lần lượt 4.58/5.37/8.70 giây. Replay gồm retrieval/adapter; không là live TTD hoặc thời gian người dùng chẩn đoán.

Gói dùng 3 generation và 1 embedding mới (B2); B3 dùng cache embedding truy vấn có sẵn. SDK không trả usage embedding nên không ghi token/chi phí đó là 0. Cache làm khác điều kiện timing giữa B2/B3; không suy ra thời gian khác biệt chỉ do RAG/modalities.

## Tái kiểm tra và phạm vi

```bash
.venv/bin/python experiments/evaluate.py experiments/cpu-comparison-evaluation.json --output results/evaluation/cpu-comparison-B1-B2-B3.json
```

Lệnh trên chỉ chấm offline, không gọi Gemini. Runner cloud đã có execution journal exclusive; không chạy lại gói để vượt số lần được duyệt.

Report/context: `results/diagnoses/CTX-0043135a9e0a5209/B1/`, `B2/`, `B3/`. Bảng máy đọc: `results/evaluation/cpu-comparison-summary.json`. Ground truth và evaluation manifest không đưa vào context hoặc Qdrant.

Scorer ghi Top-1/Top-3 B1=0/1, B2=0/1, B3=1/1. Wilson 95% cho 1/1 khoảng [20,7%;100%], cho 0/1 khoảng [0%;79,3%]. Không kết luận accuracy tổng thể, hiệu quả RAG, ROI hay cải thiện có ý nghĩa thống kê từ một ca. Official admitted vẫn **0/200**.

Bước tiếp theo: cải thiện chọn evidence có limit/baseline tương ứng với service nổi bật, kiểm soát nhiễu nền, kiểm tra dài hạn và hoàn thiện generalized runner/admission trước bộ thực nghiệm. Gói API này đã dùng hết ba lượt generation được duyệt; chưa gửi case khác.

Kiểm tra UI sau chạy: đọc đủ B1/B2/B3 mới và B3 cũ; AppTest không exception. Mở report không tăng ledger generation (4 trước/sau) hoặc embedding ledger (2 trước/sau).
