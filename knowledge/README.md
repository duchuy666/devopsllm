# Tri thức chẩn đoán

Năm runbook nháp bao phủ năm biến thể thuộc ba fault class đã chốt. Chưa runbook nào được xác thực bằng case thật hoặc index vào Qdrant.

Không đưa dữ liệu trong `docs/progress`, `chaos`, ground truth hay audit hạ tầng vào knowledge base. Chỉ index tài liệu được cho phép rõ ràng và case thuộc reference split.

Trước khi đổi trạng thái runbook thành validated: chạy scenario, kiểm tra query/metric thực tế, xác nhận evidence và cách phục hồi, ghi review cùng version. Các nguồn tài liệu trong runbook cần được đối chiếu với phiên bản cài đặt.
