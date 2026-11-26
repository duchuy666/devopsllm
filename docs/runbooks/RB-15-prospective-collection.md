# RB 15 — Thu 200 ca theo protocol đã ghim

Người dùng xác nhận bản nộp cuối bắt buộc đủ 200 ca, hạn hai ngày, có một người review độc lập. Không giảm mục tiêu hoặc tự admission.

## Release đang dùng

`results/collection-releases/20261124-prospective-v3/release.json` ghim 50 file và giữ bản sao nguồn ở `sources/`. Plan 0.3 có 200 cấu hình danh nghĩa khác nhau, ba nhóm 67/67/66, grouped split 120/40/40. Trước khi mở validation/test, 48 lượt Pod chưa chạy được đổi traffic pause để đáp ứng mục 5.3 của bản Word; bảy ca reference giữ nguyên setting được chuyển tiếp với release hash gốc. `migration.json` giữ đối chiếu và bản release v1 vẫn được bảo toàn. Không coi 200 setting là 200 cơ chế lỗi độc lập. Lịch gồm 66 batch; reference trước, validation sau, test cuối; mỗi batch tối đa bốn ca, Pod failure cuối batch.

Đây là precommitment cho thu dữ liệu và pipeline đánh giá, không phải independent review hoặc benchmark đã hoàn tất. Việc thu held-out được cho phép bởi release có hash; không chỉnh prompt, threshold, context hoặc KB sau khi truy cập test. Validation trong lịch này không được dùng để sửa pipeline sau khi đã mở test.

## Observation dùng cho benchmark

Chốt trước đợt thu: 30 giây trước đến 30 giây sau `injection_confirmed_at`, giữ span đã kết thúc trước cutoff. Tất cả cấu hình B0–B3 phải dùng cùng observation này. Mốc inject dùng để định nghĩa cửa sổ offline; không gửi loại lỗi/target/chaos/qdisc vào model context, không gọi đó là live LLM TTD. Các fault ngắn hoặc detector miss vẫn phải được báo cáo.

Raw toàn lượt ở `telemetry/` phục vụ review tác động và recovery. Dữ liệu model ở `observation/telemetry/`. Source hashes được giữ; source cap/incomplete, cửa sổ không phủ đủ hoặc thiếu modality khiến attempt không được tính capture hoàn chỉnh.

## Chạy và theo dõi

```bash
/bin/bash
source scripts/common.sh
caffeinate -di .venv/bin/python scripts/run_dataset_collection.py   --release results/collection-releases/20261124-prospective-v3/release.json   --execute --max-cases 200 --inherit-journal results/collection-releases/20261124-prospective-v3/predecessor-handoff.json
```

Luồng v2 ở `results/dataset-collection/20261123T122308Z/journal.json` đã dừng ở S0009 do collector OOM. V3 dùng predecessor-handoff trong release để giữ 10 reference capture, không giữ lượt S0009 lỗi như capture. Journal v3 mới có timestamp lúc khởi chạy; xem journal mới nhất trong `results/dataset-collection/`. Collector 0.3.1 giới hạn một job thu đồng thời và RAM 512 MiB; backup SQLite, kiểm chứng ba capture manual và soak được lưu ở `results/collector-oom-recovery/`. Query, cutoff, prompt và KB không đổi. Sự khác nhau về dịch vụ hỗ trợ phải được công bố khi phân tích.

Không khởi động thêm một controller khi luồng này còn chạy. Source thay đổi, soak/health/UTC/cleanup lỗi hoặc structural review không đạt sẽ dừng luồng; không tự retry. Giữ mọi attempt lỗi.

Chỉ sau khi đã kiểm tra và xử lý nguyên nhân dừng, có thể resume cùng release:

```bash
caffeinate -di .venv/bin/python scripts/run_dataset_collection.py   --release results/collection-releases/20261124-prospective-v3/release.json   --execute --max-cases 200 --resume results/dataset-collection/<journal-v3>
```

Nếu journal còn attempt `started`, phải đối chiếu cleanup/ground truth và đăng ký attempt trước resume; tool từ chối tự bỏ qua. Không xóa lock hoặc dùng SIGKILL để ép chạy. Trường hợp ngắt soak cần kiểm tra tiến trình traffic đã kết thúc trước lần đo mới; receipt incomplete không được dùng.

## Review và admission

Mỗi ca có `review-packet.json`, structural checks, target metric phases và các đường dẫn bằng chứng. Người review phải tự kiểm tra effect đúng target, recovery, relevance và near duplicate. Một reviewer độc lập được bố trí cho admission; chấm claim theo rubric hai người cần thêm phiếu thực tế, không dựng số liệu đồng thuận.

Nếu reviewer cũng tham gia đo thời gian, phải hoàn tất toàn bộ phiên 14 nhiệm vụ ẩn đáp án trước khi xem bất kỳ ground truth test nào. Reference/validation có thể review song song; test chờ kết thúc phiên. Xem RB16.

Reviewer chỉ điền phần `independent_review` với reviewer ID/pseudonym thực tế, timestamp có timezone, quyết định, bốn check, lý do và vị trí raw source. Không sửa scenario hoặc dữ liệu observation. Ví dụ vị trí bằng chứng: `{"file":"telemetry/metrics.json","pointer":"/memory/response/data/result/0"}`.

Preview sau khi có review thực tế:

```bash
.venv/bin/python scripts/apply_admission_review.py   --candidate data/candidates/<candidate> --review <review-packet-da-dien>.json
```

Không có `--apply` thì không sửa dữ liệu. Tool từ chối review pending/thiếu, dữ liệu đổi, case failed/development cũ hoặc scenario đã có attempt admitted. Nó tái dựng observation từ raw để kiểm cutoff, kiểm provenance và plan.

Khi controller đã kết thúc hoặc dừng an toàn, thêm `--apply` để ghi quyết định. Tool khóa registry trong lúc apply; không ghi đè registry khi controller đang thu. Các file ground truth/effect/registry/handoff/receipt được cập nhật qua transaction có backup; exception được rollback. Mất điện/SIGKILL cần đối chiếu transaction log trước khi tiếp tục, không mặc định transaction đã hoàn tất.

### Từ 200 capture đến 200 admitted

Capture đủ 200 không tự thành 200 ca admitted. Vòng lặp cho đến khi đủ:

1. `make review-queue` — chép phiếu trống cho ca mới capture vào `results/review-handoff/prospective-review/`, không ghi đè phiếu đã điền.
2. Reviewer điền phiếu ở tab **Review dữ liệu** (test chỉ mở sau khi xong phiên đo RB16).
3. `make admission-preview` — chạy toàn bộ kiểm tra của `apply_admission_review.py` cho mọi phiếu `approved` đầy đủ, không sửa dữ liệu; báo số sẽ admit, số bị từ chối kèm lý do, và số còn thiếu tới 200.
4. Khi controller đã dừng ở checkpoint an toàn: `make admission-apply` — mỗi ca một transaction riêng, ca lỗi không chặn ca khác, mỗi scenario tối đa một attempt admitted; receipt lưu ở `results/admission-batches/`. Lệnh thoát mã 1 nếu có ca bị từ chối.

Ca `rejected` hoặc phiếu thiếu trường không bao giờ được tính.

**Quy tắc thu lại (chốt ngày 25/11/2026, trước khi có ca nào bị từ chối và trước khi mở test):** scenario chỉ được thu lại khi mọi capture của nó đã bị reviewer từ chối với reviewer ID, timestamp và lý do. Lần thu lại dùng đúng dòng plan, cùng release v3, soak 600 giây mới, không đổi setting, prompt, context hoặc KB. Attempt cũ được giữ trong registry và báo cáo; ca mới phải được review độc lập lại. Số lần thu lại mỗi split được công bố khi phân tích. Chạy sau khi controller chính dừng:

```bash
bash -c 'source scripts/common.sh; .venv/bin/python scripts/recapture_rejected.py --release results/collection-releases/20261124-prospective-v3/release.json --scenario-id S00xx --reason "<quyết định của người điều phối>"'
```

Không có `--execute` thì chỉ preview điều kiện. Script nằm ngoài controller đã ghim hash nên release v3 vẫn hợp lệ; log ở `results/recaptures/`. Tổng quan hiển thị funnel capture → chờ review → duyệt chờ apply → bị từ chối → admitted.

Phiếu có đủ trường không xác thực danh tính người điền; người điều phối chịu trách nhiệm về tính độc lập và việc review đã diễn ra. Admission không phải kết quả chẩn đoán đúng. Chỉ khi đủ 200 ca được duyệt mới ghi đủ admission; benchmark và grounding/human evaluation vẫn là các mốc riêng.

## Giới hạn phạm vi hiện tại

Controller không gọi Gemini hoặc index Qdrant. Các gói Gemini trước đã dùng hết; benchmark sau cần packet và phạm vi API được duyệt riêng. Không thêm test case vào KB. Source/KB hiện được giữ nguyên, phiếu review không tự đổi trạng thái frontmatter hoặc reindex.
