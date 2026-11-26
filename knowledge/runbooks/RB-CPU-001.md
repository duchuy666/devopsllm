---
runbook_id: RB-CPU-001
version: 0.1.0
fault_class: Resource Exhaustion
variant: cpu
scope: Kubernetes application workloads
status: draft_unvalidated
---
# Chẩn đoán CPU exhaustion

## Triệu chứng

Request chậm hoặc timeout; CPU tăng, có thể chạm limit hoặc bị throttling. Một triệu chứng riêng lẻ chưa đủ xác định nguyên nhân gốc.

## Bằng chứng và chẩn đoán

1. Xác định namespace, service, Pod UID, container và khoảng thời gian. So sánh với baseline dưới cùng traffic profile.
2. Kiểm tra CPU usage theo container, request/limit và CPU throttling nếu nguồn metric hỗ trợ. Không đồng nhất usage/request cao với cạn CPU.
3. Đối chiếu latency và error rate của service với thời điểm CPU biến động.
4. Kiểm tra span ở service mục tiêu và dependency, phân biệt service chậm do tự xử lý với chờ downstream.
5. Kiểm tra CPU của node và các workload khác. Nếu cả node bão hòa, ghi nhận nhiễu testbed thay vì quy toàn bộ cho service.

## Nguyên nhân dễ nhầm

Network delay, downstream chậm, GC/memory pressure, traffic tăng, thiếu CPU ở node, chi phí giả lập AMD64 trên ARM64.

## Khuyến nghị xử lý

Kỹ sư kiểm tra workload, traffic và resource limit. Trong testbed, kết thúc stress theo runbook chaos rồi kiểm tra lại; không tự động tăng limit, scale hoặc sửa deployment khi đang thu benchmark.

## Xác nhận phục hồi

CPU/throttling và latency trở về dải baseline trong cửa sổ healthy đã định nghĩa; traffic tiếp tục thành công. Lưu evidence ID, truy vấn, timestamp và kết quả kiểm tra.

## Khi chưa đủ dữ liệu

Không có metric CPU hoặc không tách được node contention: ghi thiếu bằng chứng và giữ các giả thuyết thay thế.

## Nguồn

https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/
