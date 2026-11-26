# Giao diện, B0 và so sánh đa nhóm lỗi

Mốc mới nhất ngày 23/11: tổng 25 report; B3 đúng 2/2 ca mạng development với context 0.4.1/prompt 0.2, các giả thuyết bổ sung còn cần review. [Chi tiết](GEMINI-NETWORK-V041.md). Các số 19 report bên dưới thuộc mốc trước đợt này.

Cập nhật ngày 22/11/2026, giờ Việt Nam. Sản phẩm local đã có giao diện để sử dụng và hồ sơ kiểm chứng; thực nghiệm khóa luận chưa hoàn tất 200 ca chính thức.

## Mở sản phẩm

Truy cập http://127.0.0.1:8501. Khi cần khởi động lại:

```bash
bash scripts/run_ui.sh
```

Sáu tab: Tổng quan, Incident, Phân tích, Báo cáo, Runbook, Dataset & kiểm thử. Overview lấy số liệu từ artifact thật; Incident đọc collector hiện tại. Phân tích hiển thị bằng chứng, tải context/index và chạy B0 local. Báo cáo đọc các lần Gemini đã lưu, không tự gọi API. Mỗi lần bấm chẩn đoán Gemini là một lần gửi context qua API; không dùng nút này như refresh.

Đã kiểm AppTest không exception trước đợt cache cutover, đủ 19 report options, chạy B0 bằng browser và đối chiếu kết quả shipping CPU/limit; không phát sinh API từ thao tác xem/B0. Mốc23/11 có57unit test đạt, AppTest6tab không exception. Tracing frontend/collector0.3 đã triển khai thật; context0.4.1 giữ edge quan sát. Xem RB13. UI không hiển thị key hoặc đọc ground truth vào context.

## B0 đã có triển khai

`app/baseline.py`, phiên bản b0-rules-0.1, nhận cùng observed context: resource peak/limit >=75%, Pod not Ready/restart tăng, latency >250ms. Ranking theo score giảm dần rồi service/fault/evidence; gộp cùng service/fault, tối đa 3 giả thuyết. Latency đơn lẻ trả Unknown, không đoán network edge. Không có xác suất đã hiệu chỉnh; confidence đặt 0 và ghi rõ.

```bash
.venv/bin/python scripts/run_baseline.py
```

B0 development trên 7 lượt capture: Top-1 và Top-3 đúng 3/7; bốn lượt mạng abstain/không khớp target+class. Có replication và observation sau recovery, chưa là benchmark frozen. Ranking đã được định nghĩa nhưng cần validation trước official test.

## Bốn gói Gemini mới đã được duyệt và chạy

User duyệt cụ thể gói `results/approval/gemini-multifault-20261122`: tối đa 12 generation/8 query embedding, không retry/reindex. Đã hoàn tất 12 generation, 6 query embedding mới và 2 cache hit; không chạy lại khi kết quả sai. Packet, prompt/context cũ giữ nguyên.

| Ca reference | B0 | B1 | B2 | B3 |
|---|---|---|---|---|
| Memory payment | Đúng | Sai target | Sai target | Đúng |
| Delay orders → shipping | Không khớp/abstain | Sai target | Sai target | Đúng nhóm lỗi nhưng chỉ chọn shipping; sai directed edge |
| Loss front-end → carts | Không khớp/abstain | Sai target | Sai target | Chọn queue-master đầu; có front-end ở giả thuyết sau nhưng thiếu edge |
| Pod failure user | Đúng | Đúng | Đúng | Đúng |

Theo tiêu chí target/edge **và** class: B0 2/4, B1 1/4, B2 1/4, B3 2/4 Top-1; các lỗi mạng vẫn không khớp Top-3. Mẫu development rất nhỏ, không kết luận accuracy tổng thể hoặc lợi ích có ý nghĩa thống kê. Lỗi nền queue-master có thật; chọn sai sự cố inject không tự đồng nghĩa hallucination. Grounding cần chấm độc lập theo claim.

Generation estimate đợt mới **0,0888855 USD**; tổng 19 generation đã lưu **0,1461105 USD**. Dùng paid-standard pricing đã lưu ngày 20/11; không phải hóa đơn và chưa gồm embedding/index. SDK embedding usage chưa có số token, không coi chi phí bằng 0. Đây là replay processing, chưa đo live LLM TTD.

Artifact: `results/evaluation/multifault-b0-b3-development.json`, `results/evaluation/b0-development.json`, `experiments/multifault-development-evaluation.json` và các packet execution journal. Các phạm vi cloud đã dùng hết generation được duyệt.

## Bộ nhớ database

Readback phát hiện user-db MongoDB 3.2.10 có WiredTiger cache max 4 GiB; carts-db/orders-db 3.4.24 khoảng 3,37 GiB mỗi instance, trong khi limit container 512 MiB. Đã áp dụng runtime `cache_size=128M` cho ba instance và đọc lại đúng 134.217.728 byte, không restart hoặc xóa dữ liệu.

```bash
bash -c 'source scripts/common.sh; .venv/bin/python scripts/configure_db_cache.py'
bash -c 'source scripts/common.sh; .venv/bin/python scripts/configure_db_cache.py --apply'
```

Setter runtime riêng lẻ mất khi mongod restart. Mốc tiếp theo đã bổ sung postStart hook để tự áp cache128MiB; backup/restore và readback sau rollout cả ba DB đạt, xem [cache persistence](DB-CACHE-PERSISTENCE.md). Cache không phải giới hạn toàn bộ RSS; chưa chứng minh cache là nguyên nhân của các OOM cũ. Không thay version MongoDB hoặc schema một cách ngầm định. Tham khảo [MongoDB container/cache guidance](https://www.mongodb.com/docs/manual/reference/configuration-options/) và [runtime configuration issue của MongoDB](https://jira.mongodb.org/browse/SERVER-19483); bằng chứng phiên bản cũ dựa trên readback local, không áp dụng mù default của MongoDB mới.

Soak sau cache `20261122T060932Z` đạt 600 giây, 21 mẫu, health issues rỗng. Receipt này có trước rollout trace user/collector; không dùng receipt cũ để inject tiếp vì Pod UID/manifest đã thay đổi. Cần soak mới trước batch chaos kế tiếp.

## Trace user và collector 0.2.0

Đã bật biến ZIPKIN của native user qua tracer có sẵn trong source. Exporter local và collector 0.2.0 query cả orders/user, deduplicate theo traceId/spanId, ghi số trace từng query, lỗi và giới hạn; metadata incomplete làm collector partial. Front-end chưa instrumentation đầy đủ.

Rollout `results/product-rollout/20261122T062013Z` có backup/rollback; 3/3 checkout, 25 request, 0 lỗi sau rollout. Jaeger đã có user; export thực tế thấy carts/orders/payment/shipping/user, 62 trace duy nhất/652 span, orders query 40 trace và user query 25 (có trace trùng giữa query), không incomplete. Health issues rỗng, collector readback version 0.2.0. Tunnel collector cũ đã được reconnect sau thay Pod.

Các artifact/report trước rollout giữ nguyên; không gán trace mới vào các context đã gửi Gemini hoặc tính chúng lại như cùng một observation. Bật user tracing không đồng nghĩa đã hoàn thiện tracing toàn topology.

Capture manual bổ sung chưa thực hiện: ban đầu bị giới hạn automatic approval review; sau khi hệ thống thực thi hoạt động lại, người dùng chọn tiếp tục phần local. Không tính manual capture chưa chạy thành kết quả thành công. Fresh soak sau Mongo cutover cũng chưa đạt; receipt cũ không còn hợp lệ cho batch mới.

## Những phần chưa thể ghi là hoàn tất

- Official dataset vẫn 0/200: cần thu thực tế, kiểm tra và admission; 200 server dry-run không thay thế bước này.
- Trace front-end và ổn định dài hạn còn giới hạn; MySQL catalogue-db có OOM mới cần điều tra. Cache startup Mongo đã triển khai nhưng chưa chứng minh hết OOM toàn testbed.
- Protocol, cutoff và toàn bộ KB/prompt/model chưa được freeze cho official test; hash candidate không phải trạng thái frozen.
- Independent admission/grounding review và human baseline cần đánh giá người thật; không tạo số đo giả.

Đã chuẩn bị `results/review-handoff/`: admission-review.json, claim-review-template.json, human-session-template.json và freeze-candidate.json. Tất cả trường review/người/thời gian chưa quan sát để null/pending; không tự tăng official count. Dùng bộ này để hoàn tất review và chốt protocol trước khi mở rộng batch chính thức.
