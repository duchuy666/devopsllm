# RB12 — MySQL catalogue-db: bộ nhớ, backup và cutover

Mốc triển khai ngày 23/11/2026 theo giờ Việt Nam; artifact UTC. Giữ nguyên pinned image MySQL5.7.17 và limit512MiB. Thay đổi cấu hình là biện pháp giảm áp lực bộ nhớ, chưa phải chứng minh nguyên nhân duy nhất hoặc đã hết OOM dài hạn.

## Cấu hình đã kiểm chứng

`infra/sock-shop/mysql-memory.cnf`: buffer pool/chunk64MiB, một instance, max_connections30, temporary tables8MiB, giảm cache bảng/thread và tắt query cache/Performance Schema. Đã đọc bản gốc: buffer pool/chunk128MiB, max_connections151, max_used_connections2 và Performance SchemaON.

MySQL5.7 chỉ đổi chunk size và Performance Schema ở startup; xem [InnoDB parameters](https://docs.oracle.com/cd/E17952_01/mysql-5.7-en/innodb-parameters.html) và [Performance Schema configuration](https://dev.mysql.com/doc/mysql-perfschema-excerpt/5.7/en/performance-schema-system-variables.html). Image thật đã xác nhận `/etc/mysql/my.cnf` include `/etc/mysql/conf.d/`; mount config read-only qua ConfigMap, không thay entrypoint hoặc script seed.

## Trình tự và bằng chứng

1. Backup `mysql` và `socksdb`, file mode0600, hash archive; mật khẩu lấy từ môi trường **trong container**, không in vào argv/chat.
2. Restore vào Pod cô lập cùng image và credential configuration, có emptyDir riêng và label không được Service ứng dụng chọn.
3. Chờ readiness TCP3306 để tránh server tạm `--skip-networking` trong init; xác nhận version/config. Restore SQL, đối chiếu số dòng, DDL hash, CHECKSUM TABLE EXTENDED và hash thông tin authentication của account.
4. Khi proof đạt: quiesce frontend/catalogue, backup mới sau dừng writer; server dry-run rồi rollout đúng Deployment/ConfigMap.
5. Đọc lại config, restore backup mới, đối chiếu inventory trước mở writer; kiểm service convergence và checkout. Chỉ sau đạt mới bật source policy.

```bash
bash -c 'source scripts/common.sh; .venv/bin/python scripts/verify_mysql_policy.py'
bash -c 'source scripts/common.sh; .venv/bin/python scripts/deploy_mysql_policy.py --verification results/mysql-verification/<run>/result.json'
```

Proof và config/image phải khớp. Không dùng lệnh này như nút restart thường xuyên vì storage testbed là ephemeral. Restore lỗi hoặc apply timeout không được coi là chưa có thay đổi: script giữ writer quiesced, giữ backup và journal để phục hồi. Nếu backup lỗi trước rollout thì khôi phục writer, không đụng DB.

## Kết quả đã chạy

Proof `results/mysql-verification/20261122T170827Z/result.json` đạt restore/config/TCP, temporary resources được cleanup. Cutover `results/mysql-cutover/20261122T171041Z/result.json` đạt; 3/3 checkout,25 request,0 lỗi.

Inventory sau restore: sock9 dòng, tag11, sock_tag23; DDL/checksum/account hash khớp bản trước rollout. CHECKSUM TABLE không phải hash mật mã của toàn bộ database; không phóng đại thành chứng minh mọi giá trị bằng tuyệt đối chỉ từ checksum.

Source policy hiện enabled=true. Có readiness probe TCP; khi review log phải phân biệt health probe và lỗi ứng dụng thật. Không tăng limit RAM hoặc đổi MySQL version để đạt smoke.

## Nghiệm thu ổn định

Cần receipt mới sau rollout. Đợt3segment cũ không có health issue nhưng có gap UTC dài; xem temporal-review, không dùng làm bằng chứng30phút liên tục. Gate `utc-active-v1` mới kiểm độ liên tục sample và chênh UTC/active timer; dừng nếu có ngắt dài. Keep máy không ngủ trong lúc đo. Soak ngắn đạt vẫn chưa chứng minh không OOM qua nhiều giờ/ngày.

Mốc này không gọi thêm Gemini hoặc tự admission case. Giá trị latency/cost/accuracy của các report trước thay đổi môi trường được giữ nguyên, không gán vào môi trường mới.
