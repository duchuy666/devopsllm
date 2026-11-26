---
runbook_id: RB-NET-LOSS-001
version: 0.1.0
fault_class: Network Delay / Packet Loss
variant: packet_loss
scope: Directed service-to-service communication
status: draft_unvalidated
---
# Chẩn đoán packet loss

## Triệu chứng

Timeout, retry, lỗi kết nối hoặc latency dao động. Mất gói có thể được TCP truyền lại nên không luôn tạo HTTP error.

## Bằng chứng và chẩn đoán

1. Xác định source/destination, hướng tác động và time window.
2. Kiểm tra lỗi/retry theo endpoint và trace liên quan.
3. Nếu có metric retransmission/drop, xác nhận đo ở cấp nào: node, interface hay workload. Không gán số liệu node cho một service nếu chưa đủ căn cứ.
4. Kiểm tra sức khỏe Pod, CPU/RAM, DNS và downstream để phân biệt outage hoặc overload.
5. Không suy luận tỷ lệ packet loss chính xác từ số request lỗi. Không đưa cấu hình NetworkChaos vào context của trợ lý để chứng minh đáp án.

## Nguyên nhân dễ nhầm

Network delay, service unavailable, DNS, connection reset và ứng dụng chủ động trả lỗi.

## Khuyến nghị xử lý

Kiểm tra kết nối và tài nguyên mạng có liên quan. Trong testbed cleanup NetworkChaos, giữ nguyên traffic để kiểm tra phục hồi; kỹ sư xác nhận mọi thay đổi cấu hình.

## Xác nhận phục hồi

Không còn chaos hoạt động; lỗi/retry và latency trở về baseline; nếu có số liệu drop/retransmit thì kiểm tra đồng thời.

## Khi chưa đủ dữ liệu

Nếu chỉ quan sát timeout và không có bằng chứng phân biệt, báo bất thường đường truyền với các giả thuyết, không khẳng định packet loss.

## Nguồn

https://chaos-mesh.org/docs/simulate-network-chaos-on-kubernetes/
