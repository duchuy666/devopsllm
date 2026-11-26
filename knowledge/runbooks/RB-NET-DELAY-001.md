---
runbook_id: RB-NET-DELAY-001
version: 0.1.0
fault_class: Network Delay / Packet Loss
variant: delay
scope: Directed service-to-service communication
status: draft_unvalidated
---
# Chẩn đoán network delay

## Triệu chứng

Request chậm, timeout hoặc retry trên một đường gọi service. Trace duration tăng chưa đủ chứng minh mạng bị delay.

## Bằng chứng và chẩn đoán

1. Xác định cặp source/destination, hướng gọi, endpoint và khoảng thời gian từ telemetry quan sát được.
2. So sánh client/server span nếu có, xác nhận propagation và sai lệch timestamp trước khi diễn giải chênh lệch.
3. Đối chiếu latency/error rate với CPU, RAM và thời gian xử lý downstream để loại trừ các nguyên nhân có bằng chứng khác.
4. Tìm timeout/retry ở log đúng service và timestamp. Không coi các dòng lặp lại là nhiều bằng chứng độc lập.
5. Nếu có số liệu mạng hoặc phép đo kết nối, ghi rõ phạm vi và nguồn. Nếu không có, kết luận ở mức giả thuyết thay vì xác nhận delay mạng chỉ từ trace.

## Nguyên nhân dễ nhầm

CPU throttling, database chậm, connection pool cạn, DNS, packet loss và timeout phía ứng dụng.

## Khuyến nghị xử lý

Kỹ sư kiểm tra đường gọi, chính sách mạng và dependency; trong testbed dừng NetworkChaos theo quy trình. Không tăng timeout hàng loạt để che triệu chứng khi thu dữ liệu.

## Xác nhận phục hồi

Cùng traffic profile, latency và lỗi trở lại baseline sau cleanup; không còn NetworkChaos hoạt động trên target.

## Khi chưa đủ dữ liệu

Không có tín hiệu phân biệt: trả các giả thuyết được xếp hạng và chỉ rõ thiếu bằng chứng về mạng.

## Nguồn

https://chaos-mesh.org/docs/simulate-network-chaos-on-kubernetes/
