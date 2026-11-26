# RB 04 Chạy pilot chaos và phục hồi

## Phạm vi

Chỉ cluster `shyn-thesis`, namespace `sock-shop`. Không dùng kubeconfig production. Script từ chối chạy nếu có StressChaos, NetworkChaos hoặc PodChaos còn tồn tại trong namespace.

## Chuẩn bị

Sock Shop rollout và checkout smoke đạt; telemetry check đạt; monitoring, frontend và collector port-forward đang chạy. Xác nhận không có node contention hoặc thao tác cài đặt khác làm nhiễu baseline. Chaos Mesh dùng containerd socket của node, không dùng Docker socket của macOS.

## Chạy tuần tự

```bash
.venv/bin/python scripts/run_pilot.py cpu
.venv/bin/python scripts/run_pilot.py memory
.venv/bin/python scripts/run_pilot.py network-delay
.venv/bin/python scripts/run_pilot.py network-loss
.venv/bin/python scripts/run_pilot.py pod-failure
```

Chạy từng lệnh sau khi lệnh trước hoàn tất và hệ thống healthy. Traffic chỉ tạo tài khoản/đơn hàng giả trong Sock Shop local.

Memory pilot cấp tải 140 MB cho payment có limit 200 MiB; chẩn đoán là memory pressure nếu chưa có OOM, không tự gọi đó là OOM. Network loss dùng tỷ lệ cấu hình 20%; tỷ lệ HTTP lỗi không phải tỷ lệ packet loss. Script cố đọc qdisc counter trong namespace mạng frontend để xác minh có packet bị drop. Counter và cấu hình qdisc chỉ dùng review ground truth, không đưa vào context LLM.

Mỗi pilot có warm-up 30 giây, chờ controller xác nhận AllInjected, quan sát lỗi và recovery 35 giây. CPU/delay có duration tự hết 60 giây; Pod kill là tác động tức thời, không được diễn giải là Pod ngừng toàn bộ 60 giây.

## Đầu ra

`data/pilot/PILOT-.../` chứa ground truth, manifest inject, status controller, Pod trước/sau, traffic và thư mục telemetry. Ground truth không được đưa vào context LLM hay Qdrant test. Pilot là development data, chưa mặc định thuộc 200 case chính thức.

## Điều kiện nghiệm thu từng case

1. Controller xác nhận inject, có target thật trong status.
2. Telemetry có tín hiệu liên quan đúng target và đúng thời gian, không chỉ có dữ liệu chung.
3. Traffic thực sự đi qua đường gọi chịu tác động.
4. Ghi nhận alert bắt được hay bỏ sót; không loại ca chỉ vì detector bỏ sót.
5. Cleanup hoàn tất và Pod Ready; chạy lại smoke để xác nhận nghiệp vụ phục hồi.
6. Kiểm tra giới hạn log/trace; case thiếu dữ liệu có cờ chất lượng riêng.

`injected` trong ground truth chỉ là xác nhận controller. `admission_status: requires_review` phải được rà soát trước khi tính case hợp lệ. Chưa có review thì không báo đã đủ dataset.

## Khi lỗi

Script cố gắng xóa đúng chaos resource đã tạo trong finally. Nếu cleanup lỗi, dừng tất cả pilot tiếp theo và kiểm tra resource/status/controller; không chạy xóa hàng loạt namespace hoặc volume.

Khi người dùng ngắt tiến trình trước finally, kiểm tra tài nguyên chaos còn lại bằng kubectl. CPU/delay tự hết theo duration nhưng vẫn cần xác nhận recovery và dọn resource đúng tên.

Lưu trường hợp inject thất bại, telemetry thiếu hoặc app chưa phục hồi thành kết quả pilot lỗi; không gán ground truth thành công chỉ từ YAML.

## Các lỗi pilot đã gặp

- Controller thiếu quyền đọc RemoteCluster/Namespace: RBAC bổ sung chỉ get/list/watch, giữ quyền inject trong sock-shop.
- NetworkChaos chỉ match Pod IP không tác động traffic qua Service: resolve ClusterIP vào externalTargets; xác nhận hiệu ứng thay vì chỉ tin AllInjected.
- Webhook từ chối kết nối khi controller mất leader lease lúc node chậm: một controller dùng leaderElection=false; không bỏ validation webhook.
- Snapshot collector qua port-forward lỗi sau rollout: tách lỗi supplemental snapshot với telemetry chính, dùng tunnel tự nối lại. Giữ nguyên lỗi lịch sử; snapshot lấy lại không biến thành đúng thời điểm cũ.
- OOM nền của user ngoài chaos: ngày 20/11 điều chỉnh limit 200Mi thành 384Mi và tăng tolerance probe. Pilot cũ thuộc cấu hình cũ. Phải soak/đo lại baseline trước batch; không tự coi đây là đã sửa triệt để rò RAM.

Script hiện dry-run server trước khi tạo traffic/inject. Chi tiết kết quả từng lần nằm trong `docs/progress/PILOT-REVIEW.md`.
