# RB11 — Cache MongoDB bền vững sau restart

Trạng thái: đã kiểm chứng backup/restore cô lập cho ba MongoDB, rollout hook và restore dữ liệu sau quiesce. Cache khởi động đọc lại đúng 128 MiB; source policy enabled=true. Chi tiết [mốc triển khai](../progress/DB-CACHE-PERSISTENCE.md). Soak mới sau cutover còn pending; không suy ra cache là nguyên nhân duy nhất của OOM trước đó.

## Chuẩn bị

```bash
.venv/bin/python scripts/prepare_db_cache_rollout.py
```

Lệnh chỉ đọc local và dựng packet tại `results/db-cache-rollout/<UTC>/`. `database-only.yaml` gồm đúng một ConfigMap và ba Deployment user-db/carts-db/orders-db trong sock-shop. Không áp dụng full-preview vì full manifest có thể thay replica của writer đang được quiesce. Bản đầu được chuẩn bị khi enabled=false; sau cutover đã chuyển enabled=true.

Hook giữ nguyên entrypoint, args, seed-data command và volume hiện có. ConfigMap chỉ mount thêm script read-only. Sau khi mongod lên, script dùng timeout 5 giây cho mỗi lần gọi shell, tối đa 30 lần và sleep 1 giây giữa lần; tổng thời gian có giới hạn. Chỉ thành công khi setter trả ok và serverStatus xác nhận 134.217.728 byte. Hook thất bại khiến Kubernetes không hoàn tất startup bình thường; cần xem event/log, không bỏ hook để đạt Ready giả.

## Trước rollout thật

1. Xử lý giới hạn automatic approval review nếu còn. Không dùng đường khác để lách việc xét duyệt bị lỗi.
2. Kiểm tra cluster khỏe, không chaos/soak; giữ experiment lock trong toàn bộ migration. Lưu replica thực tế, Deployment template, image digest và manifest cũ.
3. Kiểm tra các pinned image có mongo, mongodump, mongorestore, timeout. Syntax local đạt không chứng minh binary/flags có trong image cũ.
4. Quiesce writer: front-end, user, carts, orders, queue-master; lưu số replica gốc để khôi phục. Kiểm tra không còn tác vụ ghi nền trước snapshot.
5. Backup cả ba database bằng archive phù hợp phiên bản tools, file mode0600, hash và inventory namespace/collection/document/index. Không in nội dung customer/card ra chat hoặc gửi backup lên Gemini.
6. Restore thử vào instance cô lập cùng version, không được chọn bởi Service của ứng dụng. So sánh inventory và giữ backup gốc. Chỉ tiếp tục khi restore thử đạt; kiểm tra cleanup instance cô lập theo ownership.
7. Server dry-run đúng bốn resource của packet. Các mục backup/restore chưa chạy phải giữ false/pending trong execution journal.

## Rollout, restore và nghiệm thu

Công cụ đã dùng, chỉ chạy lại khi cần migration và gate trước rollout đã đạt:

```bash
bash -c 'source scripts/common.sh; .venv/bin/python scripts/verify_db_backups.py'
bash -c 'source scripts/common.sh; .venv/bin/python scripts/deploy_db_cache_policy.py --packet results/db-cache-rollout/<packet> --restore-verification results/db-backup-verification/<verification>/result.json'
```

Thay các path bằng packet và proof thật, cùng image và source manifest. Không chạy lại packet cũ khi source đã đổi. `verify_db_backups.py` chỉ tạo backup online và restore cô lập; không coi nó là backup cutover nhất quán khi writer đang ghi. Công cụ cutover lấy backup mới sau quiesce và chỉ bật writer sau khi cả ba restore đạt.

Áp ConfigMap và ba Deployment sau khi các gate trên đạt. Các DB hiện có lưu trữ ephemeral; thay Pod có thể làm mất dữ liệu runtime, nên **không rollout trước backup đã kiểm chứng**. Hook không tự thực hiện backup hay restore.

Khi DB Ready, đọc lại cache, restore dữ liệu cũ trước khi mở writer; xác minh inventory. Khôi phục đúng replica đã lưu, kiểm service convergence và checkout. Chỉ sau thành công mới đổi source policy enabled=true/status đã xác minh và tái sinh manifest canonical. Chạy soak mới vì UID/manifest đã đổi; không tái sử dụng receipt cũ.

Nếu restore hoặc dữ liệu không khớp, giữ writer quiesced, lưu trạng thái và backup để phục hồi. Không đổi journal thành success, không xóa backup hoặc dùng seed data mới thay dữ liệu cũ mà không công bố.

## Giới hạn

Cache cap không phải total RSS cap, cũng không thay thế kiểm tra OOM/restart dài hạn. Hook đã được kiểm chứng qua lần tạo Pod mới khi rollout; chưa làm bài stress dài hạn hoặc thử crash dữ liệu. Không tính packet, migration hoặc unit test thành ca dataset đã thu/admitted. Database vẫn dùng storage ephemeral của testbed; hook không biến nó thành lưu trữ bền vững.

Soak chỉ nhận 60..600 giây vì traffic driver có giới hạn 600 giây. Kiểm tra lâu hơn cần nhiều segment và công bố khoảng gián đoạn, không gọi thành đo liên tục. Preflight mới từ chối traffic nếu tunnel frontend chưa trả HTTP200; sửa tunnel trước khi chạy lại, không coi lỗi tunnel là lỗi ứng dụng.
