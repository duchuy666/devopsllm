# RB 08 Demo và phục hồi

## Chuẩn bị

Cắm nguồn máy, kiểm tra dung lượng và memory pressure. Chạy từ thư mục dự án. Không bật thêm cluster Kubernetes khác trong Docker Desktop cho demo.

## Khởi động lại

```bash
make cluster-start
make qdrant-start
make sock-shop-forward
```

Trong các terminal riêng, giữ các lệnh sau chạy:

```bash
make monitoring-forward
make collector-forward
make ui
```

## Kiểm tra

```bash
make dependencies
make smoke
make telemetry-check
make gemini-probe
```

Gemini probe và RAG index đã đạt ngày 20/11. Không cần index lại cho mỗi demo khi runbook/model/dimension không đổi; index lại có thể gọi API tính phí. Truy cập trợ lý tại http://127.0.0.1:8501, Sock Shop tại http://127.0.0.1:8080, Grafana tại http://127.0.0.1:3000 và Jaeger tại http://127.0.0.1:16686.

## Demo live

Chọn một scenario đã review, chạy một lần, quan sát alert/incident và mở evidence. Tab Incident đang thu thập cho phép chuẩn hóa telemetry trên máy; sau đó xem tại tab Phân tích dữ liệu đã lưu. Nút Chẩn đoán gửi dữ liệu tới Gemini và có thể tính phí. Việc collector tự nhận alert chưa tự động gọi LLM.

## Demo replay

Dùng telemetry đã xuất; đánh dấu replay và giữ model/KB config. Chọn case ID không tiết lộ nhãn cho người đánh giá. Chỉ mở ground truth sau khi người tham gia xác nhận chẩn đoán.

## Khi có lỗi

Tunnel collector và Sock Shop hiện tự nối lại khi Pod thay; nếu tiến trình đã dừng, chạy lại `make collector-forward` hoặc `make sock-shop-forward`. Monitoring chưa sẵn sàng: kiểm tra Pod/volume trước khi tiếp tục; không xóa PVC để sửa nhanh.

Chaos cleanup lỗi: dừng demo mới, kiểm tra đúng resource còn lại và controller. Không chạy nhiều pilot chồng nhau. API hết quota: giữ kết quả lỗi, dùng dữ liệu replay/report đã có và công bố rõ; không sinh kết quả giả.

## Dừng

Dừng traffic và các terminal port-forward/UI bằng Ctrl+C. `make cluster-stop` dừng cluster và giữ dữ liệu. Có thể dừng riêng container `shyn-qdrant` bằng Docker khi không cần; không prune volume. Sao lưu dữ liệu thực nghiệm trước thay đổi môi trường.
