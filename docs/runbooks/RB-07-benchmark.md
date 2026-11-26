# RB 07 Đóng băng và chạy benchmark

## Điều kiện

Dataset đã admission và chia tập; Gemini probe đạt; RAG đã đo trên validation; bảng giá và schema kết quả đã chốt. Đã có comparison B1–B3 trên một CPU development pilot; chưa có benchmark B0–B3 trên official test.

## Freeze

Lưu dataset/split hashes, manifest/image/chart versions, model requested/returned version, SDK lock, prompt, thinking level, embedding model/dimension, KB version, top-k, token/context limits và cache policy. Đóng băng rule/ranking B0 trước khi nhìn test.

## Chạy

B1 log-only không RAG; B2 cùng log với RAG; B3 thêm metric/trace với cùng RAG. Tất cả dùng cùng test cases và observation cutoff. Không thay model âm thầm khi lỗi quota. Lưu failed API calls và mọi retry; chưa có API response thì không tự tạo report.

## Chấm

Chấm đúng service/target hoặc cặp có hướng và fault class, Top-3, retrieval Recall@k/MRR trên nhãn tài liệu liên quan, grounding theo rubric và hallucination theo đơn vị đã định nghĩa. Evidence ID tồn tại chỉ là kiểm tra tham chiếu. Dùng người review bằng chứng hoặc quy trình chấm độc lập, không dùng model tự cho điểm làm ground truth duy nhất.

Scorer offline đã có trong `experiments/evaluate.py`, schema ví dụ `experiments/pilot-evaluation.json`. Xem [rubric](../benchmark-rubric.md). Scorer giữ missing/invalid report trong mẫu số và tính Wilson 95%; không tự chấm semantic grounding hoặc human time. Kết quả một ca CPU development ở `results/evaluation/pilot-B3.json`, chưa là benchmark test.

Báo khoảng tin cậy, kết quả từng fault class, detector coverage, telemetry completeness, lỗi API và failure cases. Kết luận cải thiện dựa trên kết quả thật, không đặt trước accuracy phải đạt.

## Thời gian và chi phí

TTD live từ alert đến report gồm thời gian chờ context, retrieval và API. Replay latency báo riêng. Đo baseline con người và thời gian có trợ lý đến cùng điểm xác nhận chẩn đoán, có protocol hạn chế nhớ đáp án. Ghi số người, số case và điều kiện đo.

Tính token input/output/thinking/cache, embedding, retry và giá hiệu lực đúng ngày; công bố free/paid tier. Giá trị giờ công cần giả định công khai và sensitivity analysis. Chưa có số đo con người thì không tuyên bố engineer-hours saved hay ROI thực nghiệm.

So sánh development hiện có: `experiments/cpu-comparison-evaluation.json`, kết quả `results/evaluation/cpu-comparison-B1-B2-B3.json`; báo cáo tại `docs/progress/CPU-COMPARISON.md`. Không gộp ba mode thành ba incident độc lập.

## Chấm retrieval từ nhãn relevance thực tế

Reviewer đánh dấu rõ đã chấm relevance và chọn các runbook liên quan trong tab Review dữ liệu. Danh sách rỗng chỉ có nghĩa không liên quan khi checkbox đã xác nhận. Không tự gán label theo fault class hoặc cosine score.

Sau admission, chạy `scripts/score_retrieval.py <manifest.json> --output <output-moi.json>` để tính Recall@3 và MRR@3 từ thứ tự knowledge trong B2/B3. Report thiếu/lỗi tính zero khi có runbook liên quan; ca không có runbook liên quan có score undefined và được đếm riêng. Label/admission pending không sinh điểm và output báo incomplete cùng coverage. Đây không thay thế chấm grounding từng claim.
