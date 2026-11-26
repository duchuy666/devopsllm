# RB 01 Chuẩn bị môi trường Mac M2

## Mục đích

Dựng môi trường cho testbed khóa luận và lưu bằng chứng tái lập. Chưa inject chaos trong mốc này.

## Điều kiện

Máy Apple M2 16 GB; kết nối Internet; Homebrew; đủ dung lượng cho image và telemetry. Không bật đồng thời Kubernetes tích hợp của Docker Desktop và Minikube cho dự án này.

## Cài đặt

```bash
brew install minikube kubectl helm
brew install --cask docker-desktop
open -a Docker
```

Hoàn tất màn hình khởi động Docker Desktop trên máy. Nếu ứng dụng yêu cầu chấp nhận điều khoản hoặc mật khẩu quản trị, người dùng thực hiện trực tiếp. Không lưu mật khẩu vào dự án.

Đặt ngân sách ban đầu Docker ở 4 CPU và 8 GB RAM. Minikube dùng 4 CPU, 7168 MiB trong Docker VM 8 GiB. Ban đầu 6144 MiB gây cgroup memory pressure/OOM ở lần chạy dài. Giữ swap container tắt. Tắt khởi động cùng macOS nếu không cần.

## Kiểm chứng

```bash
make doctor
make audit-images
```

`doctor` phải trả exit code 0 và có thông tin Docker server. `audit-images` trả 0 khi mọi image có Linux ARM64; trả 2 khi image thiếu ARM64 hoặc truy vấn lỗi. Mở JSON để phân biệt hai trường hợp. Không suy luận khả năng chạy từ tên image.

Ghim phiên bản Kubernetes sau khi đối chiếu Minikube, kubectl và Chaos Mesh. Điền `KUBERNETES_VERSION` trong `config/testbed.env`, rồi chạy `make cluster-start`. Node phải Ready.

## Lỗi và phục hồi

- Không tìm thấy Docker CLI: kiểm tra `/Applications/Docker.app/Contents/Resources/bin/docker` và thiết lập CLI trong Docker Desktop.
- Docker server chưa sẵn sàng: mở ứng dụng và hoàn tất onboarding, chạy lại doctor.
- Image AMD64: dừng trước bước triển khai; đánh giá build ARM64 từ source hoặc testbed x86-64. Ghi mọi thay đổi trước benchmark.
- Thiếu tài nguyên: dừng cluster bằng `make cluster-stop`; không xóa volume hay dữ liệu thực nghiệm để xử lý tự động.

## Bằng chứng

Lưu kết quả doctor, image audit, phiên bản Kubernetes/chart, ngân sách tài nguyên và trạng thái node trong `results/environment/`. Không lưu Docker credentials hoặc API key.
