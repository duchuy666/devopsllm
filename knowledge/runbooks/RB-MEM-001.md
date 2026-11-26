---
runbook_id: RB-MEM-001
version: 0.1.0
fault_class: Resource Exhaustion
variant: memory
scope: Kubernetes application workloads
status: draft_unvalidated
---
# Chẩn đoán memory pressure

## Triệu chứng

RAM tăng, request chậm, GC kéo dài, container bị OOMKilled hoặc Pod bị eviction. Memory pressure có thể xảy ra mà chưa có OOM.

## Bằng chứng và chẩn đoán

1. Kiểm tra memory working set/RSS theo nguồn metric hiện có, limit và baseline. Phân biệt memory container ứng dụng, container stress và toàn Pod.
2. Kiểm tra termination reason, exit code, restart và Kubernetes events theo Pod UID. Exit code riêng lẻ chưa chứng minh OOM.
3. Đối chiếu latency/log/trace cùng khoảng thời gian. Nếu Pod đã biến mất, dùng dữ liệu lưu trước khi xóa.
4. Kiểm tra node MemoryPressure và eviction để phân biệt thiếu bộ nhớ của container với thiếu bộ nhớ node.
5. Xác nhận stress đã thực sự tác động vào phạm vi tài nguyên cần đo; không suy ra ground truth từ cấu hình yêu cầu đơn thuần.

## Nguyên nhân dễ nhầm

Memory leak, cache bình thường, GC, Pod bị kill từ bên ngoài, node contention. OOM có thể làm Pod/container thất bại nhưng nhãn gốc vẫn là resource exhaustion nếu bằng chứng cho thấy thiếu bộ nhớ gây ra.

## Khuyến nghị xử lý

Kiểm tra phân bổ bộ nhớ và workload; dừng stress trong testbed. Kỹ sư quyết định điều chỉnh limit hoặc ứng dụng sau thực nghiệm. Không xóa dữ liệu database để phục hồi tự động.

## Xác nhận phục hồi

Ứng dụng Ready, request hoạt động, bộ nhớ ổn định dưới cùng tải và không phát sinh OOM/eviction mới trong cửa sổ kiểm tra.

## Khi chưa đủ dữ liệu

Thiếu termination reason hoặc metric bị mất: báo memory exhaustion là giả thuyết, không khẳng định OOM.

## Nguồn

https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/
