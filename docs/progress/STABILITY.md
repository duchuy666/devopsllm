# Kiểm tra ổn định development

Cập nhật 21/11/2026 giờ Việt Nam; tên run dùng UTC. Đây là kiểm tra ngắn, không phải admission dataset hoặc bằng chứng ổn định dài hạn.

| Run UTC | Kết quả | Checkout hoàn tất/thử | Request lỗi |
|---|---|---:|---:|
| 20261120T234152Z | failed | 93/95 | 2 |
| 20261120T235020Z | failed | 114/153 | 39 |
| 20261120T235629Z | passed_short_soak | 169/169 | 0 |

## Các thay đổi giữa các lần

- Lần 234152: node cap 6GiB, catalogue 200m/200Mi; không đạt.
- Lần 235020: node tăng 7GiB, catalogue vẫn 200m/200Mi; không đạt, catalogue chạm cap/mất Ready.
- Lần 235629: node 7GiB, catalogue 500m/384Mi; đạt kiểm tra 300 giây với 169/169 checkout, 0 request lỗi. Monitoring/chaos và ứng dụng không đổi Ready/UID/restart trong mẫu, node không thêm OOM kill, PSI full avg10 tối đa 0% trong mẫu.

Thay đổi cap catalogue cũng tạo Pod mới; do đó chưa thể tách riêng tác động của cap với hiệu ứng khởi động lại từ một lần soak. Payment từng OOM qua thời gian dài và vẫn cần điều tra/hiệu chỉnh trước batch.

Lấy mẫu 30 giây có thể bỏ sót gián đoạn ngắn. Traffic là closed-loop pause 1,5 giây, không phải benchmark fixed RPS. Giữ nguyên toàn bộ kết quả lỗi, không gộp môi trường 6GiB/7GiB như cùng cấu hình frozen.

Telemetry check sau rollout cuối: tất cả giá trị true. UI và collector trả HTTP200. Tổng generation ledger vẫn 1; gói B1–B3 mới chưa chạy.

Bằng chứng: `results/stability/<run>/result.json`, `samples.json`, `traffic.json`; tổng hợp `results/evaluation/stability-summary.json`.
