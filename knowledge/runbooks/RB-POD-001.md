---
runbook_id: RB-POD-001
version: 0.1.0
fault_class: Pod Failure
variant: pod_failure
scope: Kubernetes application workloads
status: draft_unvalidated
---
# Chẩn đoán Pod failure

## Triệu chứng

Service thiếu endpoint Ready, request lỗi, Pod bị xóa/thay thế hoặc container dừng. Pod kill có thể được replica khác che khuất nên không nhất thiết gây outage.

## Bằng chứng và chẩn đoán

1. Kiểm tra Ready/available replicas, endpoint và Pod UID theo thời gian.
2. Kiểm tra lifecycle/events và termination reason. Khi Pod bị xóa và tạo mới, restart count trên Pod mới có thể bằng 0.
3. Đối chiếu log trước termination, metric và trace upstream để xác định service bị ảnh hưởng và thời gian gián đoạn.
4. Phân biệt Pod kill, container restart, lỗi readiness, rolling update, OOM và eviction. Không kết luận CrashLoopBackOff chỉ từ một lần Pod bị kill.
5. Phân biệt root-cause service với service upstream chỉ bị lỗi lan truyền.

## Nguyên nhân dễ nhầm

OOM từ resource exhaustion, node failure, deployment rollout, lỗi ứng dụng và network partition.

## Khuyến nghị xử lý

Kiểm tra controller và desired replicas; trong testbed kết thúc PodChaos đúng scenario. Không chạy delete hàng loạt hoặc restart toàn namespace để phục hồi.

## Xác nhận phục hồi

Controller đạt số replica mong muốn, endpoint Ready, traffic hoạt động và không tiếp tục có lần gián đoạn mới trong cửa sổ kiểm tra.

## Khi chưa đủ dữ liệu

Nếu thiếu lifecycle/event của Pod cũ, nêu rõ giới hạn và không suy ra nguyên nhân kill từ triệu chứng request lỗi.

## Nguồn

https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/

https://chaos-mesh.org/docs/simulate-pod-chaos-on-kubernetes/
