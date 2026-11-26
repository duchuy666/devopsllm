# RB 05 Cấu hình Gemini và RAG

## Phạm vi và trạng thái

Provider đã chuyển sang Gemini theo yêu cầu người dùng. Probe model đạt, 5 runbook đã được embedding/index vào Qdrant. Một chẩn đoán B3 replay trên CPU pilot đã gọi API thật thành công sau khi người dùng duyệt context. Top-1 payment / Resource Exhaustion khớp lỗi tiêm. Đây là kiểm thử tích hợp một ca, chưa phải benchmark accuracy.

## Chuẩn bị key

Mở `.env` trong thư mục dự án, điền `GEMINI_API_KEY`. Không gửi key trong chat, commit Git hoặc đưa vào manifest Docker. File được tạo với quyền 600 và được gitignore; giữ nguyên các biến cấu hình khác cho lần kiểm tra đầu.

Model ứng viên `gemini-3.8-flash`; embedding `gemini-embedding-001`, 768 chiều. Xác minh quyền truy cập thực tế, lưu model version trả về và pin cấu hình trước khi chạy tập test.

## Kiểm tra và index

```bash
make gemini-probe
make qdrant-start
make rag-index
```

Probe chỉ đọc metadata model, chưa sinh chẩn đoán. Index gửi nội dung năm runbook đến Gemini embedding API; vectors được chuẩn hóa và lưu trong Qdrant local. Runbook hiện là draft; cần review trước khi freeze KB. Cả embedding và generation có thể phát sinh chi phí theo tài khoản Google.

Không có key thì dừng trước API call. Khi model/config embedding thay đổi, tạo index tương ứng; không trộn vector khác model hoặc chiều. Retrieval lọc KB version và role reference_runbook; chưa index incident test hoặc ground truth.

## Chạy phân tích

```bash
.venv/bin/python scripts/build_context.py <thu_muc_telemetry>
.venv/bin/python scripts/diagnose.py <thu_muc_telemetry> --mode B1
.venv/bin/python scripts/diagnose.py <thu_muc_telemetry> --mode B2
.venv/bin/python scripts/diagnose.py <thu_muc_telemetry> --mode B3
make ui
```

Thay `<thu_muc_telemetry>` bằng đường dẫn có metrics.json, logs.json và traces.json. Context builder chỉ đọc ba file này; ID sinh từ hash observation, không từ tên pilot chứa nhãn lỗi. Chỉ mục evidence được lưu riêng. Log nhạy cảm được giảm thiểu/redact trước khi gửi.

B1 dùng log; B2 dùng cùng log và RAG; B3 dùng log, metric, trace và cùng RAG. LangChain core nối context, retrieval và adapter Gemini. Mỗi lần gọi diagnose chỉ có một generation, chưa tự retry hoặc tự sửa schema. Chẩn đoán bị từ chối nếu evidence ID không tồn tại; kiểm tra này không thay thế chấm grounding thủ công.

## Bằng chứng và chi phí

Lưu context, report, tài liệu truy xuất, model requested/returned version, thinking level, prompt version, token usage và latency trong `results/diagnoses/`. Thời gian replay tách khỏi TTD live.

CPU pilot đã dùng 14.146 input và 612 output token; API 7,78 giây, toàn luồng replay 8,71 giây. Ước tính generation theo paid standard ngày 20/11/2026 là 0,0129045 USD, chưa gồm embedding/index và chưa đối chiếu hóa đơn. `api_cost_usd` vẫn null; giá tham chiếu trong `config/gemini-pricing.json` có thời hạn. Không suy ra miễn phí hoặc tổng chi phí dự án từ con số này.

Report lưu ở `results/diagnoses/CTX-780d7195ef4231ff/B3/result.json`. Context cũ v0.1 được giữ cùng report; context builder hiện v0.2 có HTTP metric và hash payload/config. Không ghép report cũ với context mới. Chỉ xem tab Report đã lưu sẽ không gọi thêm API.

Lần chấp thuận ban đầu của người dùng chỉ áp dụng context CPU cụ thể trong `results/approval/gemini-cpu-pilot/`. Không dùng nó để gửi context mới, chạy lại generation hoặc batch B1–B3. Chuẩn bị payload, số lần gọi và ngân sách để người dùng review trước các lượt cloud tiếp theo.

## Khắc phục

401/403: kiểm tra key/quyền. 404: kiểm tra model ID. 429: giữ nguyên kết quả lỗi và quota, không chuyển model âm thầm. Response không đúng schema hoặc evidence không tồn tại: ghi lần chạy không hợp lệ, không thay bằng câu trả lời tự tạo.

Nếu đổi model, cập nhật config/protocol rồi chạy lại các cấu hình so sánh tương ứng. Không thay model giữa B1–B3 trên cùng tập test.

## Chuẩn bị gói so sánh trước khi gửi

```bash
.venv/bin/python scripts/prepare_comparison.py <thu_muc_telemetry> --output <thu_muc_goi_moi>
.venv/bin/python scripts/run_approved_comparison.py --approved-packet <thu_muc_goi_moi> --check-only
```

Hai lệnh trên chỉ chuẩn bị/kiểm tra local: lưu context thực cho B1/B2/B3, truy vấn embedding, 5 runbook được phép, hash và ngân sách request. B1/B2 dùng cùng log; B3 cùng observation thêm metric/trace. Gói `results/approval/gemini-cpu-comparison-20261121` đã được duyệt và hoàn tất ngày 22/11/2026: 3 generation, 1 embedding mới, B3 query cache hit; không retry. Xem `docs/progress/CPU-COMPARISON.md`. Không chạy lại runner để vượt phạm vi này.

Chỉ sau khi người dùng chấp thuận chính gói đó mới bỏ `--check-only`. Runner kiểm hash/config/KB và runbook được retrieve; tối đa 3 generation/2 query embedding, không reindex/retry. Tạo journal exclusive trước call, dừng khi lỗi và không ghi đè report. Runner đã kiểm thử cloud thành công cho gói đã duyệt. Check-only vẫn chỉ kiểm tra local, không tự chứng minh kết quả Gemini.
