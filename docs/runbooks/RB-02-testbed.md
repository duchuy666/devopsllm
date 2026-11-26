# RB 02 Khởi động và kiểm thử Sock Shop

## Điều kiện

RB 01 đạt; Docker engine chạy; cluster `shyn-thesis` Ready; dependency Python testbed nằm trong `.venv`. Máy có hỗ trợ chạy AMD64 qua lớp giả lập, được xác nhận bằng payment preflight. Cấu hình hiện tại phục vụ phát triển và phải công bố giả lập trong benchmark.

## Khởi động

```bash
make cluster-start
make sock-shop-deploy
```

Script dùng kubeconfig riêng `.runtime/kubeconfig`. Không cần thay context Kubernetes mặc định của tài khoản. Upstream được giữ nguyên; manifest triển khai sinh ra ở `infra/sock-shop/local-emulated.yaml`, các ánh xạ digest ở `images.lock.json`.

Các thay đổi có chủ ý: dùng nodeSelector ổn định; ghim digest; MongoDB 3.4.24 và Redis 4.0.14-alpine thay tag thay đổi; thêm giới hạn cho container chưa có resource budget; frontend ClusterIP; readiness của các service có probe bắt đầu sớm hơn.

## Truy cập

```bash
make sock-shop-forward
```

Giữ terminal này mở, truy cập http://127.0.0.1:8080. Chỉ bind loopback, không mở ra LAN.

Trong terminal khác ở thư mục dự án:

```bash
make smoke
.venv/bin/python traffic/run.py --profile browse --journeys 10 --seed 42 --output results/browse.json
.venv/bin/python traffic/run.py --profile checkout --workers 1 --journeys 10 --seed 42 --output results/checkout.json
```

Checkout dùng tài khoản và thông tin thẻ hoàn toàn giả trong ứng dụng demo local; payment là stub của Sock Shop. Không dùng dữ liệu cá nhân hoặc thông tin thanh toán thật. Script không tạo giao dịch thanh toán bên ngoài.

## Tiêu chí đạt

Tất cả deployment Available; kiểm tra HTTP và JSON đúng schema; hai checkout hoàn chỉnh, có order ID; không có failed request. Pod Running riêng lẻ chưa chứng minh service Java đã khởi động xong.

Trước khi thu dataset, đo healthy baseline đủ dài với traffic profile cố định, kiểm tra restart/node contention và xuất dữ liệu. Smoke-test vài request không thay thế phép đo ổn định lâu dài.

## Lỗi thường gặp

Register 500 do carts còn khởi động: kiểm tra log và readiness, chờ service thực sự sẵn sàng rồi tạo run mới. Giữ kết quả lỗi ban đầu. Nếu lỗi lặp lại, kiểm tra DNS/endpoint/database; không coi đó là incident chaos.

Tunnel frontend hiện tự nối lại khi Pod thay; nếu tiến trình đã dừng, chạy lại `make sock-shop-forward`. Traffic phải ghi lỗi phát sinh, không tự xóa các request thất bại.

## Dừng

Dừng traffic và port-forward bằng Ctrl+C, sau đó `make cluster-stop`. Thao tác này giữ lại cluster. Không chạy `minikube delete`, Docker prune hoặc xóa volume tự động.

## Ngân sách sau đo tải

Ngày 21/11 (giờ Việt Nam), cgroup Minikube 6GiB sát trần, memory.events có 12 oom_kill tích lũy và PSI full avg60 khoảng 14,8%. Đây là giới hạn container node, khác MemAvailable của VM 8GiB. Tăng riêng cap node lên 7GiB, giữ swap tắt, giữ PVC. `config/testbed.env` và start script lưu ngân sách mới; start script đồng bộ cap Docker của profile có sẵn thay vì xóa cluster.

Sau thay đổi cần `make stability`, `make smoke`, `make telemetry-check`. Kết quả trước/sau không được gộp như cùng môi trường frozen. Giữ máy cắm nguồn và thức trong thực nghiệm; có thể chạy soak bằng `caffeinate -i` trên macOS. Không coi Node MemoryPressure=False là đủ chứng minh cgroup còn headroom.

## Healthy-load gate

`make stability` phải đạt trước thu batch: không có chaos, không có thay đổi Ready/UID/restart ở Sock Shop hoặc monitoring/chaos, không thêm cgroup OOM kill, PSI memory full avg10 không vượt 5%, và checkout không có request lỗi. Đây là gate development hiện tại, cần review/freeze trước thực nghiệm. Lấy mẫu cách 30 giây có thể bỏ sót gián đoạn ngắn; đối chiếu traffic/event/metric khi review.

Không chạy build image, Helm upgrade, rollout hoặc chaos cùng soak. Khi đổi cap RAM/CPU/Pod probe, gắn môi trường mới với kết quả mới, giữ kết quả lỗi trước đó. Catalogue hiện 500m CPU/384Mi RAM sau khi baseline cũ chạm 200m/200Mi; user 384Mi; payment vẫn 200m/200Mi.
