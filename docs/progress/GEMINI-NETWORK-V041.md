# Gemini trên hai ca mạng với context 0.4.1

Ngày 23/11/2026. Người dùng đã duyệt riêng hai gói delay/loss: tối đa sáu generation và bốn query embedding, không retry hoặc reindex. Đã hoàn tất sáu generation; ba embedding mới và một cache hit giữa hai gói. Phạm vi đã sử dụng, không tự chạy lại.

## Kết quả development

| Cấu hình | Top-1 đúng target và nhóm lỗi | Top-3 | Report hợp lệ |
|---|---|---|---|
| B0 — rule local | 0/2 | 0/2 | 2/2 |
| B1 — log | 0/2 | 0/2 | 2/2 |
| B2 — log + RAG | 0/2 | 0/2 | 2/2 |
| B3 — metric + log + trace + RAG | 2/2 | 2/2 | 2/2 |

B3 xếp orders → shipping / Network Delay / Packet Loss đầu tiên ở ca delay; xếp front-end → carts / Network Delay / Packet Loss đầu tiên ở ca loss. B0 abstain với Unknown, không suy ra edge từ latency đơn lẻ. B1/B2 chọn lỗi nền queue-master; B2 ở ca loss trả Unknown nên vẫn không đúng nhóm lỗi được tiêm.

B3 còn đưa thêm giả thuyết front-end → orders và queue-master ở ca delay, queue-master ở ca loss. Top-1 đúng không chứng minh mọi giả thuyết hoặc claim đều được hỗ trợ. Cần hai người chấm grounding độc lập; evidence ID tồn tại chưa đủ để gọi claim đúng. Các giả thuyết bổ sung và chẩn đoán sai được giữ nguyên.

Cả sáu report đạt JSON schema, đúng context ID và chỉ trích evidence ID có trong context tương ứng. Prompt 0.2, context 0.4.1, model yêu cầu gemini-3.8-flash, embedding gemini-embedding-001. Không chỉnh prompt, context hoặc KB giữa sáu lần chạy.

## Thời gian và chi phí

Processing latency B1/B2/B3 của delay lần lượt 4,35 / 5,99 / 10,25 giây; loss 4,44 / 7,27 / 8,71 giây. Đây là replay processing sau khi đã có context, không phải live LLM TTD.

Generation estimate đợt này 0,0452775 USD; tổng 25 report là 0,191388 USD. Đây là ước tính paid-standard theo bảng giá có ngày kiểm chứng trong repository, chưa gồm embedding/index và chưa đối chiếu hóa đơn. Actual API cost vẫn null.

Ba query embedding mới; B2 loss dùng lại cùng query cache đã tạo cho B2 delay. Không có retry/reindex hoặc generation bổ sung.

## Giới hạn và phần còn lại

Chỉ có hai ca reference lặp lại, không phải test độc lập hoặc accuracy toàn dataset. Environment, tracing, selection và prompt cùng thay đổi so với lần cũ; không thể quy toàn bộ khác biệt cho prompt hoặc RAG. Wilson 95% của tỷ lệ 2/2 xấp xỉ 34,2–100%, thể hiện độ bất định lớn.

Các context dùng toàn cửa sổ development có recovery. Chưa có cutoff benchmark được freeze hoặc phép đo con người. Official admission vẫn 0/200; cần thu và review dataset, validation/freeze rồi mới chạy held-out test.

Phiếu review mới `results/review-handoff/claim-review-after-network-20261123/` gồm 25 report và 137 đơn vị văn bản. Người chấm phải tách claim; 137 không phải số claim. Các nhãn và điểm số còn trống.

## Bằng chứng

- Manifest chấm: `experiments/network-v041-development-evaluation.json`.
- Kết quả và Wilson CI: `results/evaluation/network-v041-b0-b3-development.json`.
- Packet, execution, authorization và usage: `results/approval/gemini-network-v041-20261123/`.
- Report gốc: `results/diagnoses/CTX-589ea93ebde2cd7f/` và `results/diagnoses/CTX-a48dc89acc015789/`.

Các report/context cũ được giữ nguyên; không gán kết quả mới sang phiên bản cũ. Giao diện đọc bảng so sánh mới và vẫn cho xem toàn bộ report đã lưu.
