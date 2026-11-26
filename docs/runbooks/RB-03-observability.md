# RB 03 Kiểm chứng observability

## Điều kiện

Cluster Ready, Sock Shop rollout hoàn tất, checkout smoke đạt. Chart/version và Helm values được lưu trong `infra/charts.lock.json` và `infra/observability/`.

## Thành phần

Prometheus thu metric; Alertmanager gửi webhook; Alloy chỉ thu log namespace Sock Shop rồi gửi Loki; Jaeger nhận Zipkin/OTLP; Grafana có datasource cho ba nguồn. Collector FastAPI lưu incident trên PVC riêng.

## Truy cập local

```bash
make monitoring-forward
```

Giữ terminal mở. Prometheus http://127.0.0.1:9090, Loki API http://127.0.0.1:3100, Jaeger http://127.0.0.1:16686, Grafana http://127.0.0.1:3000.

Grafana dùng tài khoản admin, mật khẩu được chart sinh ngẫu nhiên trong Secret. Người dùng lấy mật khẩu trực tiếp bằng kubectl với kubeconfig `.runtime/kubeconfig`; không ghi mật khẩu vào báo cáo hoặc Git.

## Kiểm chứng

```bash
make smoke
make telemetry-check
make collector-forward
```

Telemetry check phải có tất cả giá trị true, bao gồm trace có ít nhất hai service trong cùng trace ID. Kết quả lưu trong `results/environment/telemetry-check.json`. Jaeger 2.23 dùng API v3 và OTLP JSON; các script v1 dùng `/api/services` không phù hợp.

Trace hiện có ở carts, orders, shipping, payment, catalogue và user. Native user được bật ZIPKIN và kiểm chứng ngày 22/11; frontend đã có shim HTTP/B3 được xác minh bốn peer ngày23/11; không tuyên bố trace phủ toàn bộ topology. Các artifact trước mốc này giữ giới hạn coverage cũ.

## Lưu trữ và giới hạn

Prometheus/Loki retention 24h, Jaeger in-memory tối đa 5000 trace. Xuất từng case trước khi dữ liệu hết hạn hoặc Jaeger restart. Giữ query, time window và timestamp UTC.

Collector chờ 30 giây sau trigger, lấy 120 giây trước trigger, metric step 15 giây. Loki được chia cửa sổ khi chạm 5000 dòng, tối đa 32 trang; kiểm tra `log_export_incomplete`. Collector 0.3.0 query orders/user và năm profile frontend, tối đa500trace/query, chia cửa sổ khi chạm cap, tối đa32query; merge theo service/trace/span; kiểm tra export_metadata/query_errors/incomplete và `trace_limit_reached` trong capture local. Collector ghi partial khi export incomplete. Chạm giới hạn phải review, không mặc định đầy đủ. HTTP capture thành công không tự chứng minh bằng chứng đã đủ.

CPU/memory ghép với container ID hiện tại từ kube-state-metrics để tránh cộng cả container cũ sau restart. Metric có thêm latency trung bình, error rate và request rate theo service/route. Không đổi latency trung bình thành p95. Export sửa metric trong `telemetry-corrected` giữ nguyên log/trace đã lưu, vì Jaeger có thể đã loại trace cũ.

Xem [RB13](RB-13-frontend-tracing.md) cho proof, giới hạn exporter và context0.4.1.

## Alert

Rule phát triển: CPU/memory gần limit, catalogue latency trung bình trên 250 ms, front-end route `/cart` hoặc `/orders` latency mean trên 250 ms khi có ít nhất 5 request trong cửa sổ 1 phút, Pod không Ready và Pod mới tạo. Route latency giữ namespace/service/route; không gán nguyên nhân network hoặc directed edge vào alert. Pod mới tạo là tín hiệu lifecycle, không tự kết luận bị kill. Ngưỡng cần hiệu chỉnh trên reference/validation rồi freeze trước test.

Rule route mới giữ điều kiện 15 giây trước firing; scrape/evaluation đều 15 giây, rate dùng cửa sổ 1 phút. Độ trễ nhận alert còn phụ thuộc Alertmanager; không hứa phát hiện tức thì. `group_by` có service/route để không gộp các route khác nhau thành một nhóm. Không dùng counter Chaos Mesh/qdisc/ground truth để phát hiện lỗi.

```bash
make alert-test
```

Lệnh dùng promtool trong Pod Prometheus hiện có, kiểm cú pháp tất cả rule và 5 bộ dữ liệu synthetic: healthy, slow routes/pending, ít traffic, sai namespace/route, recovery. Chỉ ghi file tạm, không triển khai. Chi tiết chuẩn kiểm thử: [Prometheus rule unit testing](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/).

Live validation ngày 22/11: hai ca mạng đã tạo đúng RequestSlow `/orders` và `/cart`, collector captured; cảnh báo hết active sau recovery. Xem [bằng chứng và giới hạn](../progress/NETWORK-DETECTOR-VALIDATION.md). Đây là hai setting reference cụ thể, chưa phải coverage toàn bộ lỗi mạng.

Webhook chỉ nhận alert namespace sock-shop, chống trùng theo labels và startsAt. Trạng thái `captured` nghĩa đã lưu snapshot; chưa có LLM diagnosis.

## Lỗi

Không có trace: xác nhận traffic đi qua service đã instrumentation, cấu hình Zipkin và API v3. Log/metric rỗng: kiểm tra thời gian, label, target và trạng thái Alloy/Prometheus. Không tự thay dữ liệu thiếu bằng dữ liệu giả.

## Hiệu chỉnh memory gate và context ngày22/11

Node memory gate dùng working set ước tính từ memory.current trừ inactive_file, lưu raw/cache riêng và local OOM counters. Context builderv0.3 giữusage/limit cho top2CPU/memorypod có biến động, kể cả khi limit nằm cuối thứ tự input. Các context/report đã gọiGemini thuộcv0.1/v0.2giữ nguyên; thay policy tạoIDmới, không gán kết quả cũ vào context mới.

Repair metric cũ phải kiểm cửa sổ vẫn có dữ liệu trước khi ghi đè. Script hiện giữ export đã có nếu Prometheus hết retention hoặc query mới thiếu series; không thay bản cũ bằng kết quả rỗng.
