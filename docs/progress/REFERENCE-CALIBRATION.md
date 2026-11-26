# Reference calibration: memory, network và Pod failure

Cập nhật 22/11/2026, giờ Việt Nam. Artifact dùng UTC. Đây là kiểm tra phát triển trên testbed local; chưa phải dataset chính thức hoặc kết quả benchmark.

Mốc sau báo cáo này: đã bổ sung detector route và chạy lại hai ca mạng thành công; xem [detector validation](NETWORK-DETECTOR-VALIDATION.md). Số liệu và gap bên dưới giữ nguyên theo batch calibration ban đầu.

## Baseline và cách chạy

Soak `results/stability/20261122T030246Z`: 600 giây, 336 checkout thành công, 0 request lỗi, 21 mẫu, không có health issue. Dùng cùng manifest/native images và cap node 7 GiB. Mỗi ca kiểm receipt còn hạn, Pod UID/restart và warmup trước injection.

Batch `results/calibration-batches/20261122T031320347707Z` chạy bốn reference scenario tuần tự, không retry, Pod failure cuối. Cả bốn hoàn tất capture/cleanup/recovery; 10 structural checks mỗi ca đều đạt. Mã/cấu hình, plan và baseline receipt được lưu theo allowlist; checksum của bốn bộ provenance đã đối chiếu đạt. Không sao chép `.env`/key.

## Kết quả quan sát

| Scenario | Lỗi/mục tiêu | Bằng chứng tác động | Checkout thành công / request lỗi |
|---|---|---|---:|
| S0004 | Memory payment; thêm 150 MiB trong 90 giây | Working set từ mean nền 12,7 MiB lên peak 167,4 MiB, ba mẫu cuối mean 15,6 MiB; limit 200 MiB; không restart | 119 / 0 |
| S0078 | Delay orders → shipping; 450 ms ± 20 ms, 90 giây | Netem có 122 packet; client span `http:/shipping` từ mean 3,17 → 625,67 → 2,88 ms theo baseline/fault/recovery | 106 / 0 |
| S0071 | Loss front-end → carts; 25%, 90 giây | Netem ghi 93 drop; POST /cart mean 22,59 → 436,81 → 36,40 ms; không cộng trùng counter root/netem | 99 / 0 |
| S0135 | Pod kill user | Controller chọn Pod cũ, UID thay đổi; Pod mới Ready khoảng 6,3 giây sau yêu cầu inject; 4 lỗi POST /register trong giai đoạn fault, trước/sau 0 lỗi | 82 / 4 |

Các con số thời gian/latency là quan sát trên một ca mỗi biến thể, không phải phân phối đại diện hoặc SLA. Memory là pressure có giới hạn, chưa chứng minh memory leak/OOM. Ca mất gói có thể tăng latency dù không phát sinh HTTP error. Pod replacement không làm restartCount của container mới tăng; phải xem UID và creation/readiness.

Không có lifecycle drift ở Pod ngoài mục tiêu hoặc tăng node-local OOM trong từng ca. Snapshot cuối: 14/14 Pod ứng dụng Ready, không còn chaos, health issues rỗng. Kết quả này chưa loại trừ OOM nền dài hạn ở database AMD64 giả lập.

## Dữ liệu và giới hạn

| Scenario | Log lines | Traces | Context local v0.3 |
|---|---:|---:|---|
| S0004 | 7.686 | 238 | CTX-8f385b6a07071d0d |
| S0078 | 6.876 | 212 | CTX-34fd5851c019357c |
| S0071 | 6.431 | 198 | CTX-06a5262d92f39e9c |
| S0135 | 5.311 | 164 | CTX-190e2e42dbc74c04 |

Không có export incomplete/cap hoặc lỗi nguồn. Trace export vẫn query orders; có trace không có nghĩa đã phủ front-end/user hoặc mọi directed edge. Ground truth, controller/qdisc, review và provenance nằm ngoài context LLM. Bốn context chỉ được dựng local, **0 Gemini call mới**.

Đã đọc trigger từ SQLite collector ở chế độ read-only: memory nhận `SockShopMemoryHigh` đúng payment, 56,50 giây từ inject-confirmed tới nhận alert; Pod nhận `SockShopPodLifecycleChange` đúng Pod user mới, 32,34 giây. Đây là thời gian tới collector, không phải live LLM TTD. Không có `PodNotReady` trong cửa sổ; thời gian replacement Ready khoảng 6,3 giây ngắn hơn `for: 15s` của rule này, còn chịu ảnh hưởng scrape/evaluation timing.

Delay/loss không có incident mới trong cửa sổ. Rule latency hiện chỉ theo dõi `/catalogue`, chưa phủ hai directed edge đã thử; có khoảng trống automatic detection cho ca mạng, cần bổ sung tín hiệu phù hợp và xác thực lại. Không gán chúng thành LLM diagnosis failures vì không có lần chẩn đoán nào được chạy. Trigger evidence nằm ở batch và từng candidate, ngoài context.

Mỗi candidate có `quality-review.json` và `effect-review.json`. Assistant technical review xác nhận tác động; independent human review và admission còn pending. Registry có 6 attempt của runner mới: 1 preflight failed, 5 ca xác minh tác động phát triển gồm CPU shipping trước đó và 4 ca đợt này. **Official admitted vẫn 0/200**; 5 biến thể được kiểm chứng không có nghĩa đã thu đủ 200 case.

## Bước tiếp theo

1. Bổ sung detector cho lỗi mạng, xác thực alert timing; bổ sung coverage trace và điều tra DB OOM nền trước freeze environment.
2. Chốt admission checklist, observation cutoff, near duplicate và B0 ranking; review runbook/grounding độc lập trước benchmark.
3. Thu reference/validation/test theo grouped split 120/40/40 và 67/67/66, giữ failed attempt riêng. Pod replacement làm receipt cũ hết hiệu lực; cần soak mới trước batch kế tiếp.
4. Chỉ chạy so sánh Gemini mới khi có gói payload/model/budget được duyệt; các phạm vi duyệt trước đã dùng hết.

Chi tiết máy đọc: `results/evaluation/reference-calibration-validation.json` và `experiments/candidate-registry.json`.
