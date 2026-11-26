# Tương thích môi trường

Kiểm tra ngày 20/11/2026.

| Thành phần | Phiên bản hoặc trạng thái |
|---|---|
| Máy | Apple M2 ARM64, RAM 16 GB |
| macOS | 27.0.1 build 26A434 |
| Minikube | 1.39.0 |
| kubectl | 1.37.1 |
| Helm | 4.3.1; đã cài chart thực tế |
| Kubernetes | 1.37.0, cluster local đã chạy |
| Chaos Mesh | 2.8.8 đã cài, 5 biến thể pilot có tác động |

Theo https://chaos-mesh.org/supported-releases/, nhánh Chaos Mesh 2.8 hỗ trợ Kubernetes 1.35, 1.36, 1.37. Cần kiểm tra ba loại chaos trên môi trường thực, không suy ra hoạt động chỉ từ bảng hỗ trợ.

Kiểm tra Docker Hub cho manifest Sock Shop đã ghim: 14 image duy nhất, 3 có Linux ARM64, 11 không có ARM64. Chi tiết và digest trong `results/environment/image-audit.json`.

Không deploy upstream manifest nguyên trạng. Các image `mongo`, `kbudde/rabbitmq-exporter`, `redis:alpine` còn dùng tag thay đổi theo thời gian. Đặc biệt MongoDB hiện tại có thể không tương thích ứng dụng Sock Shop cũ; phải kiểm chứng phiên bản database khi chuẩn bị manifest thực tế.

Checkout và telemetry đa nguồn đã kiểm chứng trên testbed mixed ARM64/AMD64 emulation. Năm biến thể pilot đã quan sát tác động; chưa đủ chứng minh tính ổn định dài hạn hoặc tương đương x86 native. OOM ngoài chaos ở user yêu cầu đo lại baseline sau điều chỉnh RAM/probe trước khi freeze.
