# RB 14 — Kiểm tra điều kiện chạy benchmark

## Mục đích

Phân biệt audit dữ liệu local đạt với đủ điều kiện chạy benchmark chính thức. Tool chỉ đọc artifact và ghi báo cáo kiểm tra; không gọi API, thay cluster, admission case hoặc tự freeze cấu hình.

```bash
make benchmark-check
```

Kết quả lưu ở `results/evaluation/benchmark-readiness.json`. Exit code 0 nghĩa các điều kiện offline đạt; exit code 2 nghĩa còn điều kiện chưa đạt. Mã 2 hiện là kết quả dự kiến, không phải lỗi chương trình.

## Các điều kiện được kiểm tra

- Dataset audit không có lỗi; đủ 200 scenario chính thức, không dùng hai attempt của cùng scenario để lấp scenario còn thiếu.
- Đúng split 120 reference / 40 validation / 40 test và phân bổ nhóm lỗi 67 / 67 / 66.
- Các case admitted có provenance đã xác minh checksum. Legacy capture thiếu snapshot không được coi là đủ điều kiện chính thức chỉ vì còn raw telemetry.
- Hồ sơ admission trong `results/review-handoff/admission-review.json` khớp candidate/scenario/split/execution, có quyết định approved, người review độc lập, lý do và timestamp có timezone, không nằm trong tương lai.
- Protocol và hồ sơ freeze đều khai báo frozen; không còn pending work; các hash của plan, pipeline, manifest, cấu hình và tri thức khớp file hiện tại.
- Cấu hình ghi rõ model, embedding, KB version, cutoff, chính sách missing report và retry. Model hoặc key trong môi trường thực tế không được xác minh qua tool offline này.
- KB/index khớp source hash; từng runbook có hồ sơ review độc lập gắn với đúng nội dung đã review. Không đọc `.env` hoặc chấp nhận đường dẫn ngoài workspace làm nguồn freeze.

## Chuẩn bị trước khi điều kiện có thể đạt

1. Chốt cutoff và missing-source policy trên reference/validation. Giữ toàn lượt baseline–fault–recovery riêng cho quality review; không dùng recovery để báo live LLM TTD.
2. Thu các case còn thiếu qua runner, giữ lỗi inject/detector/export/API và provenance. Chỉ chạy sau soak đạt và kiểm health/cleanup; không chạy test trong lúc còn chỉnh prompt/threshold.
3. Người review điền quyết định thực tế vào hồ sơ admission; không sửa nhãn chỉ để tăng số lượng. Case thiếu snapshot cần chạy lại với provenance hiện tại hoặc có phương án được review rõ ràng.
4. Review năm runbook bằng `results/review-handoff/runbook-review.json`. Mỗi record có file, SHA, quyết định, reviewer, thời gian, lý do và vị trí bằng chứng. Các record hiện pending. File nằm ngoài KB; không tự đổi frontmatter thành validated hoặc reindex.
5. Khi hoàn tất các bước có bằng chứng, ghi freeze chính thức và ghim hash. Hiện `freeze-candidate.json` chỉ là ứng viên, không phải phê duyệt.
6. Chạy lại `make dataset-test` và `make benchmark-check`. Chỉ tiếp tục benchmark khi các điều kiện đạt và có phạm vi API phù hợp.

## Trạng thái ngày 23/11

10 attempt, 9 capture, 0/200 official admitted; hai ca mạng mới có B3 đúng Top-1 nhưng chưa là test accuracy. Protocol còn draft và cutoff chưa chốt. Năm runbook tri thức có phiếu review pending; KB không thay đổi và không gọi reindex.

Bổ sung bảy kiểm thử cho gate: fixture đầy đủ, count bị lấp bằng scenario trùng, nguồn thay sau freeze, review thiếu danh tính/timezone, thiếu plan pin hoặc runbook review, đường dẫn secret/ngoài workspace và legacy provenance. Fixture trong test là dữ liệu tổng hợp, không nằm trong dataset thật. Tổng Python test hiện 64 đạt.

Gate kiểm tra tính đầy đủ và nhất quán của hồ sơ; không xác thực danh tính người review. Nó cũng không kiểm live cluster/provider hoặc cấp quyền gọi API. Grounding/retrieval relevance và phiên người dùng vẫn cần đánh giá thực tế.
