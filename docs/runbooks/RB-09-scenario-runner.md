# RB 09 Runner theo scenario plan

## Phạm vi

`scripts/run_scenario.py` dựng manifest cho 200 scenario và có luồng chạy từng reference candidate. Không tự chạy cả 200, gọi Gemini hoặc admission chính thức. Đã qua unit test/mô phỏng và server dry-run; có live execution và technical effect review cho CPU shipping, memory payment, delay orders→shipping, loss front-end→carts và Pod failure user. Hai ca mạng đã chạy lặp để xác minh detector mới. Chưa xác thực mọi target/intensity hoặc admission 200 ca. Xem [calibration](../progress/REFERENCE-CALIBRATION.md) và [detector validation](../progress/NETWORK-DETECTOR-VALIDATION.md).

## Chuẩn bị

```bash
bash -c 'source scripts/common.sh; .venv/bin/python scripts/run_scenario.py --render-all --server-dry-run'
```

Đọc deployment/service thật, resolve directed edge/Service ClusterIP, lưu 200 manifest vào `.runtime/scenario-manifests/<UTC>/`. Server dry-run kiểm một đại diện mỗi biến thể, không tiêm lỗi. Không bulk-apply thư mục này. Memory chuyển từ phần trăm limit container mục tiêu thành số byte, không dùng phần trăm RAM node. Execution resolve lại IP/limit.

Chỉ xem một scenario:

```bash
bash -c 'source scripts/common.sh; .venv/bin/python scripts/run_scenario.py --scenario-id S0008'
```

## Gate trước execution

1. Không có chaos; node và toàn bộ Pod app/monitoring/chaos Ready.
2. Cgroup node còn ít nhất 5% headroom theo working set ước tính (memory.current trừ inactive_file); PSI full avg10 không quá 5%. Giữ raw usage và cache riêng; đây chưa là bảo đảm không OOM. Xem RB10 và gate version cgroup-working-set-v1.
3. Soak đạt ít nhất 600 giây, kết thúc trong 15 phút gần nhất; manifest hash, cap node, Pod UID/restart count vẫn khớp.
4. Soak ghi memory.events.local và đạt gate utc-active-v1; receipt cũ hoặc có khoảng trống UTC không cho phép injection.
5. Chỉ split reference trong protocol draft. Healthy warmup 30 giây không lỗi checkout hoặc biến động lifecycle.

Sau khi xử lý baseline và có headroom:

```bash
bash -c 'source scripts/common.sh; caffeinate -di .venv/bin/python scripts/check_stability.py --seconds 600'
bash -c 'source scripts/common.sh; caffeinate -di .venv/bin/python scripts/run_scenario.py --scenario-id S0008 --execute --stability-result results/stability/<run>/result.json'
```

Thay <run> bằng run thật. Gate không đạt thì lưu preflight_failed, không tạo traffic/chaos. Soak 10 phút vẫn là kiểm tra ngắn, chưa chứng minh ổn định nhiều giờ.

## Chống chạy chồng và cleanup

Pilot, soak và runner mới cùng giữ `.runtime/experiment.lock` bằng flock. OS nhả lock khi tiến trình kết thúc; không xóa lock để ép chạy. Không build/Helm upgrade/rollout thủ công trong lúc thực nghiệm.

Mỗi attempt có tên ngẫu nhiên và ownership label. Create timeout vẫn kiểm resource đúng tên để cleanup; timeout không chứng minh server chưa tạo. Chỉ xóa resource có ownership label khớp. SIGINT/SIGTERM đi qua cleanup; SIGKILL/máy mất điện cần kiểm tài nguyên thủ công trước thử tiếp.

## Đầu ra và review

`data/candidates/CANDIDATE-...-Sxxxx/` lưu plan hash, target/parameters, manifest, snapshot preflight/warmup/recovery, chaos status, traffic, raw telemetry. Ground truth/qdisc nằm ngoài context LLM. Thư mục ignored bởi Git.

captured_requires_review chỉ xác nhận pipeline hoàn tất, chưa xác nhận effect đúng target. Review controller target, baseline/fault/recovery, traffic qua target, ảnh hưởng ngoài target, log/trace, detector miss và near duplicate. Không tự đổi thành admitted để đạt số lượng.

Collector0.3/local exporter query orders/user và5profile frontend, có time-split cap32query. traces_present chưa chứng minh relevance với target. Candidate failed/preflight lưu riêng; official admitted vẫn 0/200.

## OOM ngày 22/11

Counter hierarchical ghi 68 oom_kill nhưng node-local bằng 0; nhiều Pod có OOMKilled. Không gọi 68 là 68 sự cố node OOM. memory.events gồm subtree; memory.events.local chỉ cấp đang đọc theo [tài liệu cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html). Runner dùng local counter để chặn node OOM và Pod state để review workload.

Trước migration native, node sát 7GiB và có OOM nền qua chạy dài. Sau migration đã có soak 600 giây đạt; chưa đủ chứng minh ổn định dài hạn để thu batch lớn. Cần điều tra memory growth/runtime/kiến trúc và xác minh lại baseline; không xóa dữ liệu hoặc bỏ gate để đạt số lượng.

## Review local sau capture

```bash
.venv/bin/python experiments/review_case.py data/candidates/<candidate>
```

Helper ghi quality-review.json ngoài telemetry/context, tổng hợp structural checks và CPU/memory/limit theo baseline–fault–recovery, Pod UID, qdisc và traffic. Kể cả checks đạt, admission vẫn requires_review; chưa tự tính vào 200. Lỗi request trong lúc fault được giữ, không tự loại. Collector snapshot/window là bằng chứng phụ, thiếu tunnel phải ghi unknown chứ không kết luận detector miss.

## Batch calibration nhỏ

Sau một soak mới đạt, có thể chạy tối đa bốn reference scenario tuần tự:

```bash
bash -c 'source scripts/common.sh; caffeinate -di .venv/bin/python scripts/run_reference_calibration.py --scenario-ids S0004 S0078 S0071 S0135 --stability-result results/stability/<run>/result.json'
```

Ví dụ gồm memory payment, delay orders→shipping, loss front-end→carts và Pod failure user. Chỉ dùng receipt thực tế vừa đạt; mỗi child vẫn kiểm gate và thời hạn 15 phút. Pod failure phải đứng cuối vì thay Pod UID. Batch dừng ngay lần đầu thất bại, không tự retry hoặc bỏ qua gate; các ca chưa chạy giữ nguyên trạng thái planned. Nếu receipt hết hạn hoặc lifecycle thay đổi thì cần điều tra và soak mới trước khi chạy phần còn lại.

Journal nằm ở `results/calibration-batches/<UTC>/batch.json`. Mỗi candidate mới có `provenance.json` và bản sao mã/cấu hình trong danh sách cho phép, scenario plan và baseline receipt. Không sao chép `.env`/key. Metadata qdisc, ground truth và provenance không phải đầu vào LLM. Batch không gọi Gemini, không index dữ liệu và không cấp admission.

## Review hai ca mạng sau instrumentation

```bash
.venv/bin/python scripts/review_network_case.py data/candidates/<candidate>
```

Helper ghi `network-observation-review.json` riêng ngoài telemetry: latency route và client span khớp edge theo baseline/fault/recovery, qdisc drop, structural checks. Phase lấy mốc injection_requested/cleanup_completed để audit, không gửi file này vào context hoặc KB. Hàm đã đối chiếu lại delay capture cũ:18baseline/38fault/49recovery span,mean5,00→594,37→3,24ms.

Kết quả tự động vẫn `observations_ready_effect_review_required`; technical effect và independent admission phải đánh giá riêng. Controller AllInjected, qdisc có counter hoặc latency tăng đơn lẻ chưa đủ xác nhận đầy đủ nguyên nhân. Bất kỳ cap/partial/exporterror cần giữ lại và review, không bỏ qua để đạt số lượng.
