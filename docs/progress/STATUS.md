# Tiến độ triển khai

## Mốc vừa kiểm chứng ngày 24/11

S0009 mới `CANDIDATE-20261124T155554622943-S0009` captured, recovery issues rỗng, structural checks đạt và observation đủ metric/log/trace. Tổng prospective 11/200; controller v3 tiếp tục S0137, admission 0/200. Mười một phiếu dữ liệu sẵn sàng cho reviewer; không gọi Gemini mới.


## Cập nhật 24/11 — khôi phục collector sau OOM

S0009 v2 đã cleanup chaos lúc 12:42:25 UTC ngày 23/11 nhưng collector OOMKilled ở 192 MiB trong recovery, nên không được tính capture hoàn chỉnh. Giữ raw, ground truth và registry lỗi. Toàn cluster hiện Ready và không còn chaos.

Collector 0.3.1 đã rollout sau backup SQLite: serialize job, ghi JSON theo luồng, RAM tối đa 512 MiB. Ba capture manual mới đạt đủ ba nguồn, không restart, RAM peak 108,76 MiB. Một probe đầu bị reset tunnel sau rollout được giữ là failed, không xóa. Soak mới 600 giây đang kiểm tra trước attempt S0009 mới. Xem [hồ sơ khôi phục](COLLECTOR-OOM-RECOVERY.md).

Release v3 ghim 50 file, giữ 10 reference với hash gốc và ghi thay đổi dịch vụ hỗ trợ; chưa mở validation/test. Offline observation, prompt, model và KB giữ nguyên. Admission 0/200, human measurements 0. Retrieval scorer đã có nhưng không điền Recall/MRR khi chưa có nhãn relevance thực tế. Tiến độ UI tự cập nhật 15 giây và hiển thị rõ khi controller dừng.


## Cập nhật 23/11 lúc 19:41 — collection và đo thời gian

Collection v2 đang chạy ở `results/dataset-collection/20261123T122308Z/journal.json`; xem journal/UI để có số thu hiện tại. Plan 0.3 có 200 setting danh nghĩa/28 họ, giữ grouped split 120/40/40 và ba nhóm 67/67/66. Trước khi mở validation/test, 48 lượt Pod chưa chạy được đổi traffic pause; bảy ca reference cũ được chuyển tiếp nguyên setting cùng hash gốc. Release v2 ghim 44 file; không thay inference/KB trong đợt thu.

Đã chuẩn bị local 8 context/B0 và packet B1–B3 từ observation được tái dựng đối chiếu raw. Chưa gửi các packet này lên Gemini và chưa chấm như benchmark. Official admission vẫn 0/200, chưa có phiếu independent review được duyệt. Các số liệu ở các mốc bên dưới là lịch sử.

Người dùng xác nhận một reviewer có thể đo trước khi xem đáp án test. Đã precommit pilot 14 nhiệm vụ, bảy cặp khác case cùng họ; UI giữ ẩn toàn bộ test ground truth tới khi kết thúc phiên. Đã có công cụ tổng hợp thời gian quan sát thật và phân tích giả định giờ công, chưa có phiên hoặc số đo người thật. Xem [RB16](../runbooks/RB-16-blind-human-timing.md).

89 kiểm thử Python đạt, giao diện tám tab đã kiểm tra bằng browser, tab đo hiển thị đúng trạng thái chờ observation/report. Có 16 runbook vận hành/5 runbook tri thức. Phụ lục phương pháp bốn trang đã render và kiểm tra; không tuyên bố đã hoàn tất thực nghiệm. Các phạm vi Gemini trước đã dùng hết.


## Kiểm tra readiness local — cập nhật sau đợt Gemini

Đã bổ sung `make benchmark-check`; kết quả hiện not_ready, đúng với thực tế: official0/200, protocol/cutoff và freeze chưa hoàn tất, năm runbook còn chờ review độc lập. Hash scenario plan đã được thêm vào hồ sơ freeze ứng viên; không admission hoặc freeze thay người review. Có14runbook vận hành,5runbook tri thức; tổng64kiểm thử Python đạt. [Quy trình mới](../runbooks/RB-14-benchmark-readiness.md).

Đã sửa `make stability` thành600giây, phù hợp gate runner. Không gọi thêm API hoặc thao tác cluster trong phần local này. Làm mới tab giao diện bị hệ thống xét duyệt chặn vì giới hạn sử dụng; chưa xác minh lại tab bằng browser sau cập nhật.


## Gemini network đã hoàn tất — cập nhật mới nhất

Đã chạy hai gói được người dùng duyệt: 6 generation, 3 query embedding mới và 1 cache hit, không retry/reindex. B3 đúng Top-1 ở 2/2 ca mạng; B0/B1/B2 đều 0/2. Đây chỉ là development, còn giả thuyết bổ sung và grounding review độc lập. Tổng 25 report; generation estimate mới 0,0452775 USD, tổng 0,191388 USD, chưa gồm embedding hoặc hóa đơn.

Xem [báo cáo Gemini network](GEMINI-NETWORK-V041.md). Phiếu review đã bổ sung đủ 25 report/137 đoạn cần tách claim. Official admission vẫn 0/200. Các mục dưới ghi lại trạng thái ở thời điểm trước lần gọi này.


## Cập nhật ngày23/11 — tracing và collector

MySQL memory policy đã qua isolated restore/TCP startup và cutover có backup/quiesce; checksum/schema/account khớp, checkout3/3/0lỗi. Mongo128MiB vẫn enabled. Soak sau MySQL `20261123T013516Z` đạt600giây gateUTC,317checkout/0lỗi; ba segment cũ có khoảng trống UTC không được tính là30phút liên tục. Xem [MySQL stability](MYSQL-STABILITY.md).

Frontend đã chạy fixture trên đúng Node4.8.0; rollout live thấy peer user/carts/orders/catalogue và15trace đa service. Collector0.3.0 capture phát triển đủ metric/log/trace,569span,không incomplete. Context0.4.1 giữ tối đa8edge client trước các span lặp;57kiểm thử Python đạt. Soak sau rollout `20261123T015437Z` đạt600giây/21mẫu,UTCspan599,97giây,maxgap30,78giây,không issue. Checkout305/0requestlỗi; xác nhận ngắn hạn. [Quy trình/proof](../runbooks/RB-13-frontend-tracing.md).

Hai reference network chạy lại trên pipeline mới đều đạt structural/effect technical review: delay client4,75→618,34→11,38ms,91checkout/0lỗi; loss client18,81→364,58→16,64ms,79drop,89checkout/0lỗi. Detector tới collector lần lượt71,40/65,96giây sau inject-confirmed. Không cap/exporterror, cuối batchhealthissuesrỗng. [Chi tiết](NETWORK-TRACING-RECALIBRATION.md).

Không gọi Gemini mới:19report cũ giữ nguyên; prompt0.2/context0.4.1 chưa được chấm lại. Registry10attempt/9capture,official0/200;13runbook vận hành và5runbook tri thức. Các mục bên dưới là lịch sử theo từng mốc; số liệu phiên bản cũ không thay cho trạng thái mới nhất này.


Cập nhật ngày 22/11/2026, giờ Việt Nam. Timestamp trong artifact dùng UTC. Sản phẩm đang phát triển; chưa hoàn tất thực nghiệm khóa luận.

## Các mốc đã kiểm chứng

| Mốc | Kết quả | Phần còn thiếu |
|---|---|---|
| M0 — môi trường | Docker VM 8 GiB, Minikube 7 GiB/4 CPU, Kubernetes 1.37 chạy trên M2 16 GB | Vẫn còn image AMD64 giả lập |
| M1 — ứng dụng | 14 deployment Sock Shop; 3 service Go đã build ARM64; checkout và soak 600 giây đạt | Ổn định nhiều giờ và lỗi nền database/queue-master |
| M2 — telemetry | Prometheus/Loki/Jaeger/Grafana, collector 0.2.0; đã có trace user, query orders/user không trùng span | Trace chưa phủ frontend đầy đủ; Jaeger in-memory |
| M3 — chaos/runner | 200/200 manifest server dry-run đạt; 5 biến thể có live effect calibration; hai ca mạng chạy lại đã tới collector | Mọi target/intensity, coverage và admission |
| M4 — trợ lý | Drain3, Qdrant 5 runbook, LangChain, Gemini, UI; context v0.3 giữ usage/limit theo Pod | Runbook còn draft, grounding/hallucination chưa chấm độc lập |
| M5 — dataset/benchmark | Plan 200 scenario/28 nhóm, structural audit đạt; scorer offline, 2 ví dụ CPU so sánh B1–B3 | **Official admitted 0/200**, B0/protocol chưa freeze, chưa official test |
| M6 — phân tích | 7 generation có report/ledger, token/latency và paid-standard estimate | Human baseline, ROI, test accuracy và hồ sơ bàn giao cuối |

## Mốc mới: native Go và độ ổn định

- Payment/catalogue/user được cross-build Linux ARM64 từ source tag và dependency commit đã ghim, dùng Go 1.23.12. Phần còn lại vẫn có giả lập AMD64.
- User có compatibility patch xuất trường `href` để giữ JSON contract cũ; Go unit test package users đạt. Hai migration lỗi đã rollback và giữ bằng chứng; lần thứ ba đạt 2/2 checkout, 18 request, 0 lỗi.
- Soak `20261121T232358Z`: **600 giây, 327 checkout, 0 request lỗi**, 21 mẫu; working set 83,8–88,5%, PSI full avg10 max 0,01%, node-local OOM kill không tăng.
- Gate dùng working set ước tính `memory.current - inactive_file`; lưu cả raw/cache riêng. Counter OOM trước đây là hierarchical, gồm cả cgroup con; không được suy ra tất cả là node OOM. Gate mới dùng `memory.events.local`.
- Qua các lần chạy dài trước migration có OOM ở payment, catalogue, user và một số database. Soak mới chỉ xác nhận ngắn hạn, chưa chứng minh lỗi dài hạn đã hết.

## Runner và reference calibration

S0011, CPU shipping 90 giây, đã qua fresh receipt/warmup, controller xác nhận đúng target, cleanup và recovery đạt. CPU từ baseline mean 0,00594 lên peak 0,99898 core trên limit 1 core; các mẫu cuối trở về gần nền.

Có **118 checkout, 0 request lỗi**; export **7.623 log lines/236 traces**, không incomplete/cap. Structural checks đều đạt; effect được xác minh ở mức assistant technical review, independent human/admission review còn pending. Không tự tính candidate vào 200 case chính thức.

Collector nhận đúng SockShopCPUHigh của shipping sau inject-confirmed 81,65 giây; context ready sau alert-received khoảng 30,58 giây. Chưa phải live LLM TTD.

Artifact: `data/candidates/CANDIDATE-20261121T233425132808-S0011/`. Context local: `CTX-f7afb08ddfe940b4`, schema v0.3, 35 metric/15 log template/15 span.

## Mốc tiếp theo: đủ 5 biến thể calibration

Soak mới `20261122T030246Z` đạt 600 giây, 336 checkout, 0 request lỗi. Sau đó batch bốn reference scenario chạy đủ vòng, cleanup/recovery và structural checks đều đạt:

- S0004 memory payment: từ 12,7 lên 167,4 MiB rồi về 15,6 MiB; 119 checkout, 0 lỗi request.
- S0078 delay orders→shipping: client span mean 3,17 → 625,67 → 2,88 ms; 106 checkout, 0 lỗi request.
- S0071 loss front-end→carts: netem 93 drop; POST /cart mean 22,59 → 436,81 → 36,40 ms; 99 checkout, 0 lỗi request.
- S0135 Pod failure user: UID thay đổi, Pod mới Ready khoảng 6,3 giây sau yêu cầu inject; 82 checkout thành công, 4 lỗi register trong fault, trước/sau 0 lỗi.

Snapshot cuối 14/14 Pod Ready, không còn chaos, health issues rỗng. Không có non-target lifecycle drift hoặc tăng node-local OOM trong bốn ca. Đã dựng bốn context v0.3 local, không gọi thêm Gemini. Checksum provenance của bốn ca đạt.

Registry runner mới có 6 attempt: 1 preflight failed và 5 ca được assistant technical review xác minh tác động. Independent human/admission review còn pending; **official admitted 0/200**. Đã đối chiếu trigger read-only: MemoryHigh đúng payment sau inject-confirmed 56,50 giây; PodLifecycleChange đúng Pod user mới sau 32,34 giây. Không có alert delay/loss; rule latency chỉ theo dõi catalogue, còn thiếu automatic detection cho hai edge này. Chi tiết tại [reference calibration](REFERENCE-CALIBRATION.md).

## Mốc mới nhất: detector mạng và kiểm thử dataset

Đã thêm RequestSlow cho front-end `/orders` và `/cart`, dựa trên latency mean >250 ms và ít nhất 5 request/1 phút, giữ điều kiện 15 giây. Promtool kiểm cú pháp và 5 bộ dữ liệu synthetic đạt; triển khai Prometheus revision 5. Alert chỉ báo triệu chứng route chậm, không gán sẵn root cause/edge.

Soak sau triển khai `20261122T054235Z`: 600 giây, 336 checkout, 0 request lỗi, không RequestSlow firing trong baseline. Chạy lại S0078/S0071: collector nhận đúng route `/orders` sau inject-confirmed 63,60 giây và `/cart` sau 46,48 giây; cả hai captured. Collector context ready thêm khoảng 30 giây; chưa phải live LLM TTD. Cuối batch 14/14 Pod Ready, không chaos hoặc RequestSlow active. Không gọi thêm Gemini.

**200/200 manifest qua server dry-run**, plan audit và audit dữ liệu local đạt. Registry hiện có **8 attempt/7 lượt capture**, gồm hai network replication; independent review pending, **official admitted 0/200**. Exact hash không thay thế semantic near-duplicate review. Sáu candidate có provenance snapshot mới đạt checksum; CPU shipping trước đó được báo legacy thiếu snapshot kiểu mới.

Xem [detector validation](NETWORK-DETECTOR-VALIDATION.md) và [dataset validation](DATASET-VALIDATION.md). Các mô tả gap detector và số lượng 6 attempt/5 ca ở mốc trước là lịch sử trước lần bổ sung này.

## Gemini đã chạy

Cập nhật mới nhất: đã bổ sung B0 local và chạy thêm 4 gói memory/delay/loss/Pod được user duyệt: 12 generation, 6 query embedding mới và 2 cache hit; tổng hiện **19 generation**. Trên 4 ca development mới, Top-1 B0 2/4, B1 1/4, B2 1/4, B3 2/4; B3 chưa khớp directed edge ở hai ca mạng. Generation estimate đợt mới 0,0888855 USD, tổng 0,1461105 USD, chưa gồm embedding/index và chưa đối chiếu hóa đơn. Các số 7 generation bên dưới thuộc mốc CPU/shipping trước đó. Xem [product handoff](PRODUCT-HANDOFF.md).

| Gói | Kết quả trên ca development | Generation estimate USD |
|---|---|---:|
| B3 CPU ban đầu | Payment đúng Top-1; cùng underlying pilot với gói CPU sau | 0,01290450 |
| CPU B1/B2/B3 | B1/B2 chọn queue-master; B3 đúng payment / Resource Exhaustion | 0,02257125 |
| Shipping B1/B2/B3 | B1/B2 chọn queue-master; B3 đúng shipping / Resource Exhaustion | 0,02174925 |

Tổng **7 generation**, paid-standard estimate **0,057225 USD**, chưa gồm embedding/index và chưa đối chiếu hóa đơn. Hai gói so sánh đã dùng hết ba generation mỗi gói, không retry hoặc reindex. Không gửi thêm context ngoài phạm vi được duyệt.

B3 đúng trên hai ví dụ CPU chưa chứng minh accuracy tổng thể. Hai ca khác environment/context version; không gộp như một test benchmark frozen. B1/B2 chọn lỗi nền có thật nhưng không đúng sự cố CPU được tiêm; không gọi mọi chẩn đoán sai là hallucination.

Xem [CPU comparison](CPU-COMPARISON.md) và [shipping/runner comparison](SHIPPING-RUNNER-COMPARISON.md).

## Kiểm tra phần mềm và UI

Mốc mới nhất: ba MongoDB đã rollout postStart cache128MiB, backup/restore cô lập và cutover quiesced đều đạt, dữ liệu inventory khớp; 3/3 checkout,25 request,0 lỗi. Source policy enabled=true. Soak sau cutover bị dừng/incomplete do tunnel đang chuyển kết nối; chưa chạy lại theo lựa chọn tiếp tục local của người dùng. Đã bổ sung preflight HTTP200 và giới hạn soak60..600 giây. Catalogue-db MySQL có OOMKilled mới lúc2026-11-22T16:43:00Z, cần điều tra riêng. Xem [chi tiết cache persistence](DB-CACHE-PERSISTENCE.md).

Context v0.3 ưu tiên top hai Pod có CPU/memory biến động và limit tương ứng, độc lập ground truth và thứ tự metric input. Regression test giữ được payment limit 0,2 core và orders limit 1 core trong CPU pilot. Report/context v0.1/v0.2 đã gửi được giữ nguyên.

40 kiểm thử Python đạt; Go unit test package users đạt. Có kiểm thử cache hook/cutover, soak tunnel preflight, trace dedup/incomplete, B0, batch selection, provenance không sao chép key và dataset admission/registry consistency. UI có sáu tab, B0 local, audit dataset và đọc đủ 19 report; AppTest trước đợt cutover không exception, thao tác xem/B0 không phát sinh API. Trợ lý tại http://127.0.0.1:8501, Sock Shop http://127.0.0.1:8080, collector http://127.0.0.1:8000. Cần tiến trình local/port-forward còn chạy.

Collector tự nhận alert và lưu telemetry; UI chuẩn hóa local, nút Gemini là bước gửi riêng. Chưa tự động gọi LLM cho mọi alert. Ground truth/qdisc/review files nằm ngoài context và Qdrant.

## Đi tiếp theo thứ tự

1. Tiếp tục kiểm tra dài hạn, xử lý và ghi rõ lỗi nền; xác minh native environment trước freeze.
2. Mở rộng kiểm chứng theo target/intensity khi cần; detector route mới đã nhận hai ca mạng, còn trace coverage và khả năng tổng quát ngoài hai setting đã thử.
3. Chốt collection protocol, schema/version, admission và near duplicate; thu reference rồi validation/test đúng grouped split 120/40/40, giữ 67/67/66.
4. Review runbook/retrieval relevance; B0 đã triển khai development, cần validation/freeze cùng prompt, KB, model và cutoff trước test.
5. Chạy benchmark B0–B3 trên cùng test case; giữ API failures/missing reports trong mẫu số, chấm grounding/hallucination độc lập.
6. Đo thời gian người dùng thật, phân tích sai số/chi phí và hoàn thiện hồ sơ tái lập. Chưa có human measurements thì chưa kết luận saved hours/ROI.

Xem [luồng build](../BUILD-FLOW.md), [11 runbook vận hành](../runbooks/README.md), [RB09 runner](../runbooks/RB-09-scenario-runner.md), [RB10 native Go](../runbooks/RB-10-native-go.md) và [RB11 Mongo cache](../runbooks/RB-11-db-cache-persistence.md).

Soak `20261124T154551Z` đã đạt 600 giây, UTC gate đạt, 318 checkout/0 request lỗi. Journal v3 đang hoạt động: `results/dataset-collection/20261124T155554Z/journal.json`. Số capture/admission hiện tại phải đọc từ journal/registry; khởi chạy không đồng nghĩa hoàn tất.
