# Bổ sung detector và xác minh hai ca mạng

Cập nhật 22/11/2026, giờ Việt Nam. Đây là reference calibration; chưa phải benchmark trên test set frozen.

## Thay đổi

Thêm `SockShopRequestSlow` cho metric HTTP thật của front-end, route `/orders` và `/cart`. Điều kiện: latency mean cửa sổ 1 phút trên 250 ms, ít nhất 5 request trong cửa sổ, giữ 15 giây. Giữ labels namespace/service/route và bổ sung service/route vào Alertmanager grouping.

Đây là detector triệu chứng route chậm, không tự kết luận service gốc, directed edge hay phân biệt delay/loss. Không dùng ground truth, Chaos Mesh metadata hoặc qdisc để phát cảnh báo. Ngưỡng được kiểm tra trên reference development, còn cần validation/freeze trước test; chưa chứng minh coverage mọi target/intensity trong plan.

Đã kiểm cú pháp 6 rule và 5 bộ dữ liệu synthetic bằng promtool 3.16.0: healthy, slow/pending, ít traffic, sai namespace/route, recovery. Tất cả đạt. Cách kiểm thử theo [tài liệu Prometheus](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/). Triển khai riêng Prometheus chart 29.47.2, Helm revision 5; backup cấu hình trước thay đổi ở `results/detector-validation/before/`. Không xóa PVC hoặc triển khai lại toàn bộ observability.

## Baseline và live execution

Soak `20261122T054235Z`: 600 giây, 336 checkout, 0 request lỗi, 21 mẫu, health issues rỗng. Không có firing `RequestSlow` trong baseline này; một baseline ngắn chưa chứng minh false-positive rate dài hạn bằng 0.

Batch `20261122T055258250940Z` chạy lại S0078 rồi S0071, cùng target/setting của reference calibration trước:

| Quan sát | Delay orders → shipping | Loss front-end → carts |
|---|---:|---:|
| Fault | 450 ms ± 20 ms, 90 giây | 25%, 90 giây |
| Traffic qua netem / drop tại snapshot | 99 packet qua rule | 88 packet drop |
| Checkout thành công / request lỗi | 105 / 0 | 97 / 0 |
| Route alert thực tế | front-end `/orders` | front-end `/cart` |
| Inject-confirmed → collector nhận | 63,60 giây | 46,48 giây |
| Collector nhận → context ready | 30,26 giây | 30,18 giây |
| Collector status | captured | captured |
| Log lines / traces của candidate | 6.804 / 210 | 6.305 / 194 |

Delay có orders client span `http:/shipping` mean baseline/fault/recovery **5,00 → 594,37 → 3,24 ms**. Loss có POST /cart mean **34,15 → 479,05 → 23,98 ms**. Controller target, qdisc, traffic và telemetry xác nhận tác động; 10 structural checks mỗi ca đều đạt. Không có non-target lifecycle drift hoặc tăng node-local OOM.

Trigger được đọc từ SQLite collector ở chế độ read-only, đối chiếu đúng namespace/service/route và incident; timeline `ALERTS` có firing trong từng cửa sổ. Snapshot cuối: **14/14 Pod Ready, không chaos, health issues rỗng, không RequestSlow active**. Chưa ghi độc lập payload webhook resolved, nên chỉ xác nhận Prometheus hết active, không tuyên bố đã kiểm chứng delivery của resolved webhook.

Thời gian trên là alert/context latency trên hai ca local, chưa phải live LLM TTD. Không gọi Gemini mới. Hai context candidate dựng local: `CTX-f750400084273882` và `CTX-55900040e696d704`. Ground truth, trigger timing và qdisc nằm ngoài context; không sửa các gói Gemini đã duyệt trước đó.

## Hồ sơ và giới hạn còn lại

- `results/detector-validation/live-validation.json`: hai ca, trigger, manifest collector, effect review và trạng thái cuối.
- `results/detector-validation/promtool.json`: kết quả rule tests.
- `results/detector-validation/baseline-alerts.json`: firing query của baseline.
- `results/detector-validation/dataset-server-dry-run.json`: 200 manifest server dry-run.
- Từng candidate có provenance, quality/effect review, detector evidence và firing timeline. Audit checksum đạt.

Các ca chạy lại là replication trong reference, không phải hai setting lỗi mới. Dataset mới có 8 attempt/7 lượt capture, **official admitted 0/200**. Trace coverage front-end/user, ổn định DB dài hạn, independent review, B0 và protocol freeze vẫn còn. Kiểm thử dataset được ghi riêng tại [dataset validation](DATASET-VALIDATION.md).
