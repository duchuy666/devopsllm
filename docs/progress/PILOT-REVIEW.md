# Đối chiếu pilot và lỗi đã gặp

Review phát triển, cập nhật 21/11/2026; ID/timestamp pilot dùng UTC ngày 20/11. Không thay admission trong ground truth gốc và không đưa pilot vào 200 case chính thức.

## Từng lần thử

| Pilot suffix | Biến thể | Kết quả quan sát | Diễn giải |
|---|---|---|---|
| 091235-cpu | CPU | Controller không xác nhận inject | Thiếu quyền đọc cache RemoteCluster; không là ca lỗi ứng dụng đã tiêm |
| 092147-cpu | CPU | Không inject; cleanup ban đầu lỗi | Còn thiếu quyền đọc Namespace; giữ bằng chứng lỗi, đã xử lý RBAC |
| 092510-cpu | CPU | Payment CPU khoảng 0,013 → 0,198 core, limit 0,2; alert đã nhận | Có tác động; một report Gemini B3 khớp Top-1 |
| 092835-network-delay | Delay | AllInjected nhưng latency không tăng có ý nghĩa | Filter Pod IP không tác động đường Service; không dùng như positive effect case |
| 093226-pod-failure | Pod kill | Payment Pod UID đổi, Pod thay thế Ready | Có tác động lifecycle; không suy ra toàn bộ outage kéo dài 60 giây |
| 093534-network-delay | Delay | Catalogue mean latency trước 79,0ms (23 request), trong 1091,0ms (10), sau 24,7ms (40) | Sau bổ sung Service ClusterIP có tác động; mẫu nhỏ, đây là mean không phải p95 |
| 134523-memory | Memory | Payment working set baseline 22,87MiB, max 166,40MiB, limit 200MiB | Memory pressure, chưa là OOM; alert đã nhận |
| 135253-network-loss | Loss | Webhook connection refused, không inject; metric export timeout | Ca chạy lỗi hạ tầng, không là packet-loss positive |
| 141121-network-loss | Loss | qdisc báo 48 drop; 78/78 journey hoàn tất, 0 request lỗi | Có drop; TCP có thể khôi phục nên không cần HTTP error. Telemetry chính đủ; snapshot collector bổ sung bị mất tunnel |

Tổng: **9 lần thử, 5 pilot có tác động quan sát**, một lần injected nhưng không xác nhận effect, ba lần inject thất bại. Đây là review development, không phải 5 case chính thức admitted. `admission_status` lịch sử vẫn `requires_review`.

## Bằng chứng và chất lượng export

Nguồn trong `data/pilot/PILOT-20261120T<suffix>/`. Review giữ riêng manifest/ground truth/Pod state/qdisc với dữ liệu LLM. Với pilot đã có thư mục `telemetry-corrected`, dùng metric sửa container ID và log/trace được bảo toàn từ export trước; không lấy trace mới sau khi Jaeger đã evict.

| Pilot có tác động | Log lines đã export | Trace đã export | Nguồn review |
|---|---:|---:|---|
| CPU 092510 | 5736 | 174 | telemetry-corrected |
| Pod 093226 | 4209 | 125 | telemetry-corrected |
| Delay 093534 | 3806 | 114 | telemetry-corrected |
| Memory 134523 | 4804 | 146 | telemetry-corrected |
| Loss 141121 | 4232 | 124 | telemetry |

Các export trên ghi không incomplete/chạm trace cap ở bản được review. Số dòng/trace chỉ chứng minh nguồn có dữ liệu, chưa chứng minh đủ mọi bằng chứng. Context chỉ giữ một phần có chọn lọc. Các bản export cũ chạm 5000 log/100 trace được giữ nguyên, không âm thầm đổi lịch sử.

Lỗi snapshot bổ sung ở loss 141121 được giữ trong `export_error`; `collector-incidents-recovered.json` là truy vấn lại sau khi nối tunnel, không phải snapshot đúng thời điểm cũ. Không gọi toàn bộ telemetry của ca này thất bại chỉ vì bước bổ sung đó.

## Những sửa chữa quan trọng

1. RBAC controller: bổ sung quyền đọc RemoteCluster/Namespace; quyền inject vẫn giới hạn namespace.
2. Network filter: bổ sung Service IP rồi xác nhận latency/drop thực.
3. Metric cAdvisor: ghép container ID hiện tại, tránh cộng series cũ sau restart. Con số memory cũ vượt limit là lỗi phép tổng hợp, không là bằng chứng container vượt cgroup cap.
4. Loki chia cửa sổ và giữ multiplicity; Jaeger giới hạn/cờ chất lượng rõ; không ghi đè trace đã lưu bằng truy vấn mới rỗng.
5. Controller đơn tắt leader election sau mất lease; giữ webhook. Đây không thay kiểm tra node contention.
6. SDK Gemini bỏ tham số embedding không được Developer API hỗ trợ; lỗi ValueError xảy ra trước HTTP, không phải một generation thành công.
7. Port-forward collector/frontend tự nối lại khi Pod thay.
8. User OOM nền ngoài chaos lúc 14:23:24 UTC: tăng limit 200Mi → 384Mi, điều chỉnh probe. Cần baseline/soak mới; không kết luận hết rò RAM từ rollout thành công.

## Review một report Gemini

`CTX-780d7195ef4231ff/B3` là replay, context v0.1 được lưu cùng report. Top-1 payment / Resource Exhaustion khớp ground truth. Evidence E-M001/E-M040 cho usage gần limit, E-T007 cho dependency chậm; chưa có metric throttling nên không khẳng định đã chứng minh throttling.

Giả thuyết orders CPU exhaustion yếu hơn: CPU tăng chưa đồng nghĩa cạn CPU. Queue-master Docker socket là nhiễu nền có log thật, chưa chứng minh nguyên nhân của CPU pilot. Không thực thi khuyến nghị mount host Docker socket từ report.

Confidence 0,85 chưa hiệu chỉnh. Scorer offline `results/evaluation/pilot-B3.json` có Top-1/Top-3 1/1; Wilson 95% xấp xỉ [20,7%; 100%]. Không dùng kết quả một ca để công bố accuracy tổng thể. Grounding review định tính ở đây chưa là bộ nhãn được hai người chấm độc lập.

## Việc còn thiếu

- Tính ổn định dài hạn sau cấu hình mới; kiểm soát restart nền và node saturation.
- Generalized scenario runner, admission từng case, near-duplicate review và freeze.
- B0 ranking, tập test độc lập, retrieval relevance, chấm claim-level và human timing.
- Kinh phí/quyền gửi cho context mới: lần duyệt CPU đã dùng, không chạy batch Gemini dựa vào lần duyệt đó.

## Lỗi nền và cgroup sau thời gian chạy dài

Soak `results/stability/20261120T234152Z` không đạt: catalogue mất Ready và hai request HTTP500. Ngoài user OOM trước đó, payment cũng có OOM lúc 17:52:27 UTC. Không có chaos trong soak; các sự cố này không được gán nhãn injected fault.

Cgroup node sát 6GiB, memory.events ghi 12 oom_kill tích lũy (không đồng nghĩa 12 incident độc lập); PSI full avg60 ~14,8%, page reclaim lớn. MemAvailable của VM và Node MemoryPressure=False chưa phản ánh giới hạn node container. Sau tăng cap lên 7GiB, giữ swap tắt, PSI full avg10 về 0 ở mẫu kiểm tra và không tăng oom_kill. Kube-state-metrics/Alertmanager được tạo lại Pod để thoát CrashLoop; PVC không bị xóa. Telemetry check đạt lại sau phục hồi. Đây là bằng chứng hồi phục ban đầu; cần soak/baseline tiếp, không gộp môi trường 6GiB với 7GiB như cùng frozen config.

Soak thứ hai `20261120T235020Z` vẫn không đạt: catalogue chạm cả 200m CPU và gần 200MiB RAM, mất Ready/liveness restart; nhiều request checkout lỗi. Node PSI avg10 giảm nhưng chưa thể kết luận toàn hệ thống ổn định. Catalogue đã nâng riêng 500m/384Mi để thử tiếp; giữ nguyên hai kết quả soak lỗi. Không khẳng định đã tìm/sửa memory leak hoặc lỗi GC.

Soak thứ ba `20261120T235629Z` đạt 300 giây sau chỉnh catalogue: 169/169 checkout hoàn tất, 0 request lỗi, không thêm cgroup OOM kill. Không đổi Ready/UID/restart trong các mẫu của cả ứng dụng và monitoring/chaos. Kết quả này chỉ xác nhận ngắn hạn; xem `STABILITY.md`, vẫn cần xử lý nguy cơ OOM payment ở lần chạy dài.

Ngày 22/11, gói CPU B1/B2/B3 được duyệt đã chạy đủ: B1/B2 chọn queue-master/Pod Failure (sai so với fault tiêm), B3 đúng payment/Resource Exhaustion Top-1. Xem `CPU-COMPARISON.md`; một ca chưa chứng minh cải thiện tổng thể.
