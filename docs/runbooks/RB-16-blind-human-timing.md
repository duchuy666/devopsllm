# RB 16 — Đo thời gian với đáp án test ẩn

Người dùng đã xác nhận có một người review độc lập và người này có thể đo trước khi xem đáp án test. Đây là pilot 14 nhiệm vụ, bảy cặp cùng họ dùng hai ca khác nhau; mỗi cặp có một nhiệm vụ dashboard/B0 và một nhiệm vụ dashboard/B3. Không phải crossover cùng case. Protocol và thứ tự đã lưu ở `experiments/human-study-plan.json` trước khi thu test; người tham gia không đọc file mapping này.

## Chuẩn bị và thứ tự thực hiện

1. Người điều phối kiểm tra đủ observation của 40 ca test và tạo manifest bằng `scripts/prepare_prospective_benchmark.py --journal <journal> --split test`. Tool từ chối split test còn thiếu, kiểm raw/observation và không gọi API. Admission vẫn pending nếu chưa có review thực tế.
2. Chuẩn bị phạm vi Gemini mới từ các packet đã tạo, xác nhận model, số request, dữ liệu gửi và chi phí tham chiếu với người dùng. Các phạm vi trước đã dùng hết. Chỉ gọi sau khi được duyệt; không retry lỗi hoặc reindex ngoài phạm vi. Cần report B3 của bảy nhiệm vụ trợ lý trước phiên đo; không dùng ground truth để dựng report.
3. Người tham gia có thể luyện thao tác trên ca reference, sau đó vào tab **Đo thời gian** tại `http://127.0.0.1:8501`. Không xem ground truth, thư mục candidate, mapping nhiệm vụ hoặc report test bên ngoài điều kiện được phân công trước khi xong toàn bộ phiên. UI giữ ẩn test ở các tab thường; đây là kiểm soát quy trình, không phải cơ chế phân quyền filesystem.
4. Giữ máy cắm nguồn, không sleep hoặc restart Streamlit giữa phiên. Không mở developer tools chứa mapping. Người điều phối ghi sự cố nếu bị gián đoạn, giữ log cũ; không tự điền hoặc sửa số đo. Không thực hiện thay người tham gia.
5. Người tham gia tự nhập pseudonym và xác nhận đồng ý ghi thời gian, chưa xem đáp án. Chỉ bắt đầu khi sẵn sàng chẩn đoán. Nếu không biết, chọn Unknown và tự nhập target/giải thích phù hợp; không dò đáp án.
6. Ở mỗi nhiệm vụ, bấm **Bắt đầu quan sát ca này**, đọc telemetry và report của điều kiện được giao, tự nhập target/nhóm lỗi rồi bấm **Chốt chẩn đoán và kết thúc ca đo**. Bộ đếm dùng thời gian thực tế phía server. Không có phản hồi đúng/sai giữa các nhiệm vụ.
7. Sau đủ 14 nhiệm vụ, mới mở review ground truth test. Reviewer tự kiểm effect, recovery, relevance, near duplicate và runbook relevance. Admission là bước riêng, thực hiện sau khi controller kết thúc hoặc dừng an toàn; không ghi registry đồng thời với collection.

## Dữ liệu và tổng hợp

Phiên nằm ở `results/human-study/human-pilot-v1/<hash-pseudonym>/session.json`. Mỗi nhiệm vụ giữ đúng context/report đã hiển thị trong `inputs/<opaque-id>/`, kèm SHA256 trong phiên; thay đổi đầu vào bị từ chối khi hiển thị hoặc tổng hợp. Giữ bản gốc và checksum trước phân tích. Không có số đo nào chỉ vì đã mở tab; không tạo session mẫu vào thư mục kết quả thật.

```bash
.venv/bin/python scripts/summarize_human_study.py \
  --session results/human-study/human-pilot-v1/<hash-pseudonym>/session.json \
  --output results/evaluation/human-timing-observed-v1.json
```

Tool yêu cầu đủ nhiệm vụ đúng protocol/condition, consent, diagnosis và timestamp có timezone. Nó tái tính thời gian, không đọc ground truth, không gọi API, không suy ra correctness. Lệch UTC/monotonic được ghi invalid và loại rõ khỏi thống kê; không nội suy số giây. Báo mean/median từng điều kiện, chênh lệch trong từng họ và số cặp có hai thời gian hợp lệ. Chênh lệch âm được giữ.

Nếu cần phân tích nhạy cảm giờ công, thêm `--hourly-cost-vnd <gia-dinh-VND-moi-gio>` và dùng đường dẫn output mới. Giá trị này là giả định công bố, không phải đơn giá đã khảo sát. Kết quả là giá trị giờ công gộp trên một nhiệm vụ; chưa trừ API/hạ tầng/review, không phải ROI hoặc tiết kiệm production.

Thời gian đo là thao tác trên context đã tải và report trợ lý tính sẵn. Báo riêng API latency, retrieval và live alert đến report; không cộng/tráo các đại lượng này để tạo số live TTD. N=1 và hai ca trong một cặp khác setting, nên kết quả chỉ mô tả pilot, không chứng minh hiệu ứng nhân quả hay đại diện cho kỹ sư nói chung.
