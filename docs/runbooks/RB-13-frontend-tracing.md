# RB 13 Tracing frontend và xuất context

## Cấu hình đã kiểm chứng

Frontend giữ image, user, giới hạn tài nguyên và biến session cũ; Node thực tế **v4.8.0**. Preload shim ES5 bằng `node --require /opt/shyn-tracing/frontend-tracing.js server.js`. ConfigMap chỉ đọc, startup cũ được kiểm từ package trước rollout. Không nâng runtime trong bước instrumentation.

Shim theo dõi HTTP inbound/outbound, truyền B3, xuất Zipkin v1 sang Jaeger nội bộ. Chỉ giữ route chuẩn hóa, status và peer thuộc allowlist; bỏ query, headers và body. Dynamic path được thay bằng `:id`. Không suy ra topology từ ground truth. Chỉ hỗ trợ HTTP của ứng dụng hiện tại, chưa chứng minh coverage mọi giao thức.

Exporter best effort: hàng đợi tối đa1000, batch128, timeout3giây; dropped counter được log khi thay đổi. Queue đầy hoặc exporter lỗi có thể mất span. Không coi HTTP checkout đạt là trace đầy đủ.

## Thực hiện theo thứ tự

```bash
/bin/bash
source scripts/common.sh
.venv/bin/python scripts/verify_frontend_node.py --help
.venv/bin/python scripts/deploy_frontend_tracing.py --verification results/frontend-node-verification/20261123T014557Z/result.json
bash scripts/deploy_collector.sh
```

Chỉ deploy khi proof đúng image và SHA tracer hiện tại. Fixture chạy isolated cùng image/Node, kiểm sampling, concurrent context, privacy và lỗi HTTP. Deployer chỉ đổi frontend, lưu template trước đổi và tự rollback nếu smoke/live trace không đạt. Không restart database. Không thực hiện khi soak hoặc chaos đang chạy.

Proof fixture: `results/frontend-node-verification/20261123T014557Z/`. Proof live: `results/frontend-tracing-rollout/20261123T015021Z/`: checkout3/3,25request,0lỗi; client peer user/carts/orders/catalogue và15trace đa service. Đây là development verification, chưa phải benchmark.

## Collector và context

Collector0.3.0 dùng orders/user cùng5profile route frontend, tối đa500trace mỗi query,32query tổng. Query chạm cap được chia cửa sổ; không chia tiếp được thì đánh dấu incomplete/partial. Shared RPC dedup theo `(service,traceId,spanId)` để giữ quan sát ở cả caller và callee.

Capture thủ công `INC-20261123T015416-c041604b` chỉ là kiểm tra phát triển: cả ba nguồn đạt,569span,7query,không incomplete. Artifact ở `results/collector-rollout/20261123T015334Z/`.

Context0.4.1 ưu tiên tối đa8client edge quan sát, rồi các operation khác theo error/duration; tối đa15span trước cắt theo character budget. Trace bị cắt vẫn phải ghi nhận giới hạn; không bảo đảm đầy đủ topology. Chọn span không dùng target của scenario. Evidence index gồm service/trace/span để tra về raw.

Context4.0 đầu tiên bị chi phối bởi root span chậm lặp lại; giữ nguyên artifact này, tạo context4.1 mới. Context mới có tám edge từ raw thực tế. Prompt0.2 chưa được đánh giá lại bằng Gemini; không chuyển kết quả model cũ sang context mới.

## Lỗi và phục hồi

Không có frontend span: kiểm preload command, hash annotation, endpoint9411 và exporter dropped counter. Có span nhưng mất edge trong context: so raw với selection/budget; không thêm peer phỏng đoán. Collector partial: đọc query_errors/incomplete, không tự đổi thành captured. Tunnel local cũ sau rollout phải đợi supervisor reconnect; chỉ dừng child port-forward xác định thuộc dự án khi cần.

Collector giữ PVC và kiểm không còn capture queued/collecting trước rollout; script lưu deployment trước đổi và rollout undo nếu lỗi. Dữ liệu database Sock Shop vẫn ephemeral; tracing không thay đổi chính sách backup.
