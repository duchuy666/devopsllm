# MySQL memory policy và chất lượng phép đo

Cập nhật 23/11/2026, giờ Việt Nam. MySQL5.7.17 và container limit512MiB được giữ nguyên.

Đã backup/restore cô lập, kiểm TCP startup, đọc lại cấu hình64MiB pool/chunk, Performance SchemaOFF và max_connections30. Cutover có quiesce, backup mới, restore trước mở writer; dữ liệu/catalogue schema/account checks khớp, checkout3/3/25request/0lỗi. Xem [RB12](../runbooks/RB-12-mysql-memory.md).

Đợt đo `results/stability-series/20261122T171326Z` có ba segment hoàn thành theo timer active và không health issue, tổng968 checkout/0requestlỗi. Tuy nhiên review UTC tìm khoảng sample dài nhất lần lượt920,1069,1559giây; UTC span khác active timer rõ rệt. Có thể do sleep hoặc thay đổi clock; chưa kết luận chính xác nguyên nhân. **Không tính đây là30phút quan sát liên tục hoặc receipt đạt gate mới.**

Kết quả gốc được giữ nguyên; review bổ sung ở `results/stability-series/20261122T171326Z/temporal-review.json`. Không sửa số liệu cũ thành kết quả đạt.

Đã bổ sung `app/stability_timing.py` và gate `utc-active-v1`: kiểm UTC gap, clock lùi, UTC/active disagreement và sample thiếu; runner từ chối receipt cũ không có gate này. Soak mới `results/stability/20261123T013516Z` đạt gate:317checkout,0requestlỗi,21mẫu,UTCspan599,79giây,maxgap30,62giây,không node-local OOM tăng. Chỉ xác nhận ngắn hạn sau MySQL cutover.

Frontend tracing đã qua fixture đúng Node4.8 và rollout live; collector0.3 thu đủ ba nguồn. Soak sau hai rollout `20261123T015437Z` đạt600giây,UTCgate/21mẫu/không issue;checkout305/0requestlỗi. Context v0.4.1 bổ sung peer_service allowlist, span_kind và chọn edge đa dạng từ dữ liệu quan sát; prompt v0.2 hướng dẫn không đoán edge khi thiếu hai endpoint. Chưa gọi Gemini để đánh giá thay đổi này; không dùng kết quả cũ làm chứng minh prompt mới tốt hơn.
