# Quy tắc chấm benchmark — bản nháp

Chuẩn bị trước khi nhìn tập test. Protocol vẫn draft, chưa có kết quả thực nghiệm đầy đủ.

## Chẩn đoán và mẫu số

Target đúng service hoặc directed edge (source → destination) và đúng nhóm lỗi mới tính đúng. Không tính đúng edge đảo chiều hoặc chỉ đúng một đầu. Top-1 xét giả thuyết đầu; Top-3 xét tối đa ba giả thuyết.

Mẫu số là toàn bộ case admitted trong split đã khai báo, kể cả thiếu report/API lỗi/schema lỗi. Báo thêm coverage report hợp lệ; không loại API failure để tăng accuracy. Các case inject không thành công thuộc bảng chất lượng thu thập riêng; detector miss không tự động loại ca có lỗi thực.

Scorer local không gọi model:

```bash
.venv/bin/python experiments/evaluate.py experiments/pilot-evaluation.json --output results/evaluation/pilot-B3.json
```

Manifest pilot chỉ chứa một ca development được review để kiểm tra scorer, không phải test set. Official manifest phải khai báo `dataset_role: official_test`, từng case admitted/split test và context/report đúng ID. Ground truth/manifest chấm luôn nằm ngoài KB và context gửi model.

Wilson 95% cho từng tỷ lệ; khi so sánh B1/B2/B3 trên cùng case cần thêm thống kê paired và phân tích lỗi, không suy ra cải thiện chỉ từ hai con số điểm.

## Grounding và hallucination theo claim

Hai người chấm độc lập tách mỗi phát biểu thực tế trong root cause/rationale/action justification thành claim có ID. Ghi evidence được trích, vị trí raw source, nhãn và lý do. Sau đó mới đối chiếu/chốt bất đồng; công bố số người/case, mức đồng thuận và cách xử lý.

| Nhãn | Quy tắc |
|---|---|
| supported | Bằng chứng trong observation hỗ trợ phát biểu và đúng target/thời gian |
| partially_supported | Có một phần hỗ trợ, nhưng phát biểu mạnh hơn dữ liệu hoặc còn thiếu điều kiện |
| unsupported | Không có hỗ trợ đủ; gồm suy ra nhân quả từ tương quan đơn lẻ |
| contradicted | Bằng chứng quan sát mâu thuẫn phát biểu |
| unverifiable | Observation không đủ để xác minh; ghi rõ dữ liệu thiếu |

Evidence ID tồn tại không tự là supported. Đánh giá grounded claim rate = supported / toàn bộ factual claims, công bố riêng partial/unverifiable. Hallucination cần định nghĩa trước: factual detail bị dựng không có trong nguồn hoặc bị nguồn phủ định; không tự đồng nhất mọi hypothesis sai với bịa dữ kiện. Ghi hai cờ riêng: chẩn đoán đúng/sai và claim support.

Các hành động đề xuất được review tính liên quan và khả năng gây tác động; scorer không thực thi remediation. Nội dung được đánh dấu giả thuyết/khuyến nghị vẫn cần kiểm tra dữ kiện nền của phát biểu.

## Retrieval

Gán runbook liên quan bằng nhãn độc lập trên validation/test; lưu ranked runbook ID. Recall@k và MRR chỉ tính khi có bộ relevance labels đã review, không dùng cosine score thay nhãn. KB version cố định giữa B2/B3; không index case test hoặc near duplicate.

## Thời gian và con người

Lưu UTC alert received, context ready, retrieval start/end, API start/end, report ready. Live TTD = report ready − alert received; replay chỉ báo processing latency. Alert detection latency và injection-to-detection báo riêng.

Phiên người dùng ghi participant pseudonym, điều kiện B0/trợ lý, case opaque ID, bắt đầu xem dữ liệu, chẩn đoán cuối, độ đúng, thời điểm kết thúc. Counterbalance thứ tự, tránh cùng người nhìn lại cùng đáp án. Không ghi thời gian ước lượng vào cột observed. Chưa có phép đo thì để null và chưa tính saved hours/ROI thực nghiệm.

## Freeze và chất lượng

B0 đã có development implementation b0-rules-0.1 trong app/baseline.py, chưa validation/freeze cho official test. Xem [product handoff](progress/PRODUCT-HANDOFF.md). Freeze dataset/group/split hash, model/SDK/thinking, prompt/context version, KB/embedding/top-k, cutoff, token limit, traffic/environment, cache và retry policy. Báo thiếu telemetry, lỗi API và mọi thay đổi cấu hình. Không chỉnh threshold/prompt theo đáp án test rồi chấm lại như test độc lập.

## Bộ phiếu review đã chuẩn bị ngày23/11

`scripts/prepare_claim_review.py` tạo phiếu local từ đúng report/context đã lưu, không gọi API và không gán nhãn thay người. Bộ `results/review-handoff/claim-review-20261123/` gồm19report/105đơn vị văn bản. **105không phải số claim**: người chấm cần tách các phát biểu thực tế trước khi chấm. Mọi reviewer/claim label/adjudication/grounding score vẫn trống.

Phát riêng file `REVIEW-*.json` cho hai người chấm độc lập. Giữ `coordinator-manifest.json` riêng: file này ánh xạ về mode/report gốc để tổng hợp sau chấm. Mode label được bỏ khỏi phiếu nhưng modality vẫn hiện; không gọi đây là nghiên cứu mù hoàn toàn. Evidence ID chỉ hỗ trợ đối chiếu; phải tra raw source và ghi vị trí, không dùng ID tồn tại làm nhãn supported.

Bộ phiếu cập nhật sau hai gói mạng: `results/review-handoff/claim-review-after-network-20261123/`, đủ 25 report và 137 đơn vị văn bản. Không điền nhãn thay người; giữ bộ cũ cho audit.
