# Cache MongoDB sau startup và kiểm chứng dữ liệu

Cập nhật ngày 22/11/2026 theo giờ Việt Nam. Timestamp artifact dùng UTC. Không gọi thêm Gemini và không admission dataset trong mốc này.

## Đã thực hiện

1. Kiểm tra thực tế các image có timeout/mongo/mongodump/mongorestore.
2. Backup online và restore vào Pod cô lập cùng image cho user-db/carts-db/orders-db; collection/document/index inventory khớp, cleanup các Pod kiểm tra theo ownership. Production DB không bị restart trong bước này.
3. Chuẩn bị packet đúng bốn resource: ConfigMap script và ba Deployment. Hook không thay entrypoint/args hay volume dữ liệu cũ; có timeout, retry bounded và readback cache.
4. Quiesce front-end/user/carts/orders/queue-master, lưu replica cũ; lấy backup archive mới mode0600, hash và inventory sau khi dừng writer.
5. Server dry-run rồi rollout. Mỗi DB Ready, cache đọc lại **134.217.728 byte**; restore archive mới và so inventory trước khi mở writer.
6. Khôi phục replica, kiểm service convergence và checkout: **3/3 hành trình, 25 request, 0 lỗi**. Source policy chuyển enabled=true; manifest canonical có hook để các lần start sau tự cấu hình cache.

Artifact:

- `results/db-backup-verification/20261122T165105Z/result.json`: restore cô lập đạt cho ba DB.
- `results/db-cache-rollout/20261122T164858Z/execution-plan.json`: phạm vi và gate đã chuẩn bị.
- `results/db-cache-cutover/20261122T165327Z/result.json`: backup mới, restore và readback của cutover.
- `infra/sock-shop/db-cache-policy.json`: trạng thái đã kích hoạt.

Backup chứa dữ liệu runtime local, không gửi cloud hoặc index vào RAG. Hash archive xác nhận file được giữ nguyên; so inventory không thay thế chứng minh equality của mọi giá trị document. Không gọi migration thành ba case lỗi chính thức.

## Gate và kiểm thử local

**40 Python test đạt**, gồm bảo toàn entrypoint/volume, scope namespace, không thay hook có sẵn; backup thất bại thì không rollout DB; restore thất bại thì không mở writer; tunnel lỗi hoặc HTTP503 không khởi động soak traffic. Audit dataset hiện 8 attempt/7 capture, official0/200, không lỗi cấu trúc.

Một đợt soak mới đã dừng sớm ở `results/stability/20261122T165528Z`: tunnel frontend đang chuyển kết nối sau thay Pod. Kết quả được giữ là failed/incomplete, không dùng làm receipt đạt. Đã bổ sung preflight HTTP200 trước khi traffic hoặc sampling cluster. Chưa chạy lại soak sau khi người dùng chọn tiếp tục phần local; không sử dụng receipt cũ trước cutover.

## Vấn đề mới cần giữ riêng

Read-only snapshot ghi catalogue-db OOMKilled lúc **2026-11-22T16:43:00Z**, restartCount2; Pod sau đó Running/Ready. Đây là MySQL, không thuộc ba MongoDB vừa cấu hình. Buffer pool quan sát128MiB, max_connections151 và performance_schemaON; chưa kết luận cấu hình nào gây OOM hoặc đã khắc phục MySQL. Cần điều tra và test dài hạn trước khi freeze môi trường.

Theo lựa chọn mới nhất của người dùng, công việc hiện chỉ tiếp tục ở mã/tài liệu/kiểm thử local. Đánh giá lại MySQL, kiểm tra dài hạn, manual capture bổ sung và các batch mới trên cluster chưa thực hiện trong phần local này.
