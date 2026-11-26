# RB 17 — Tự chạy các ca và kiểm tra đầu ra

Hướng dẫn cho workspace `/Users/cloudino/Documents/ChatGPT/shyn`. Release đang dùng: `results/collection-releases/20261124-prospective-v3/release.json`. Journal hoạt động lúc viết: `results/dataset-collection/20261124T155554Z/journal.json`. Phải đọc trạng thái thực tế trước khi chạy; số ca có thể tăng sau khi lưu hướng dẫn.

## 1. Phân biệt các mốc

- Scenario: một dòng trong kế hoạch 200 setting. Không phải đã thực thi.
- Attempt: một lần chạy; chạy lại cùng scenario tạo thư mục mới. Giữ cả attempt lỗi.
- Captured: runner hoàn tất, raw và observation đủ điều kiện kỹ thuật. Chưa chứng minh effect đúng hoặc review độc lập.
- Admitted: người review thực tế đã duyệt, công cụ admission đã áp dụng và registry khớp. Không tự tăng số này.
- Benchmark: chẩn đoán B0–B3 trên cùng 40 ca test và cùng observation, chấm so với nhãn đã duyệt. Không lấy accuracy development thay test.

Luồng tổng thể: kiểm môi trường → soak → traffic baseline → inject → fault observation → cleanup → recovery/traffic kết thúc → xuất raw → crop observation → structural check → review → admission → benchmark và phân tích. Phiên đo người phải diễn ra trước khi người tham gia xem ground truth test.

## 2. Chuẩn bị máy và terminal

Cắm nguồn, giữ máy thức và không đóng nắp. Docker Desktop cần chạy; cấu hình hiện tại Docker VM 8 GiB, Minikube 7 GiB/bốn CPU. Dọn dung lượng bằng cách di chuyển file cá nhân không liên quan nếu cần; không xóa raw, PVC, Docker volume hoặc backup của dự án để lấy chỗ.

Mở Terminal:

```bash
cd /Users/cloudino/Documents/ChatGPT/shyn
/bin/bash
source scripts/common.sh
export SHYN_RELEASE="$PWD/results/collection-releases/20261124-prospective-v3/release.json"
export SHYN_JOURNAL="$PWD/results/dataset-collection/20261124T155554Z"
```

Mỗi terminal mới phải `cd` và `source scripts/common.sh` lại. Không in `.env` hoặc gửi key trong chat. Thu dataset, audit và B0 không cần gọi Gemini.

## 3. Xem trạng thái trước khi làm gì khác

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path
p=sorted(Path('results/dataset-collection').glob('*/journal.json'))[-1]
j=json.loads(p.read_text())
done={a['scenario_id'] for a in j['attempts'] if a['status']=='captured_requires_review'}
r=json.loads(Path('experiments/candidate-registry.json').read_text())
print('Journal:',p)
print('Trạng thái:',j['status'])
print('Prospective captured:',len(done),'/200')
print('Admitted:',r['official_admitted'],'/200')
print('Lượt cuối:',j['attempts'][-1] if j['attempts'] else None)
print('Lỗi:',j.get('error'))
PY
```

Nếu `running`, không khởi động controller, soak hoặc runner thứ hai. Có thể theo dõi và review reference/validation. Giao diện Tổng quan tự cập nhật tiến độ mỗi 15 giây khi trang mở. Nếu mất terminal nhưng journal vẫn `running`, kiểm tra thêm tiến trình; journal là trạng thái lưu, không phải bằng chứng tiến trình còn sống:

```bash
ps -axo pid,ppid,command | rg 'run_dataset_collection.py|run_scenario.py|check_stability.py|traffic/steady.py'
```

Không dùng `pkill python`, không xóa lock để ép chạy. Nếu không còn tiến trình mà journal vẫn `running`/attempt còn `started`, phải đối chiếu dữ liệu, cleanup và registry trước resume; không tự sửa `started` thành thành công.

## 4. Kiểm môi trường và các tunnel

Chỉ kiểm tra; các lệnh này không inject:

```bash
kubectl --context=shyn-thesis get nodes
kubectl --context=shyn-thesis get pods -n sock-shop
kubectl --context=shyn-thesis get pods -n monitoring
kubectl --context=shyn-thesis get pods -n chaos-mesh
kubectl --context=shyn-thesis -n sock-shop get stresschaos,networkchaos,podchaos
```

Trước một đợt mới: Node Ready, các Pod app/support Ready, không còn chaos. Trong lúc fault đang chạy, chaos tồn tại và Pod target có thể đổi trạng thái là dự kiến; không tự xóa hoặc restart khi controller còn sở hữu lượt đó.

Nếu cluster đang dừng và không còn đợt thực nghiệm hoạt động, mở Docker Desktop rồi chạy `bash scripts/start_cluster.sh`. Không deploy lại toàn bộ ứng dụng/database để xử lý một tunnel lỗi. Restart database cần quy trình backup/restore riêng.

Nếu cổng đã hoạt động, giữ tiến trình hiện có. Nếu thiếu, mở từng lệnh sau trong terminal riêng, từ thư mục dự án:

```bash
bash scripts/port_forward.sh
```

```bash
bash scripts/forward_monitoring.sh
```

```bash
bash scripts/forward_collector.sh
```

```bash
bash scripts/run_ui.sh
```

Kiểm cổng:

```bash
curl --fail --max-time 5 http://127.0.0.1:8080/ -o /dev/null
curl --fail --max-time 5 http://127.0.0.1:8000/health
curl --fail --max-time 5 http://127.0.0.1:9090/-/ready
curl --fail --max-time 5 http://127.0.0.1:3100/ready
curl --fail --max-time 5 http://127.0.0.1:16686/api/services
```

Sock Shop: 8080; trợ lý: 8501; collector: 8000; Prometheus: 9090; Loki: 3100; Jaeger: 16686; Grafana: 3000. Health endpoint thành công chưa chứng minh telemetry của một case đủ hoặc đúng.

Không cần chạy `gemini-probe` hoặc `rag-index` để thu case. Những lệnh đó có thể gọi API, còn reindex làm đổi KB.

## 5. Cách nên dùng: controller tự thu theo kế hoạch

### Đang chạy

Để controller hiện tại tiếp tục. Không chạy lại lệnh start chỉ để xem tiến độ.

### Tiếp tục một journal đã dừng

Sau khi đã xử lý lỗi, xác nhận không còn tiến trình của lượt cũ và chaos đã cleanup:

```bash
caffeinate -di .venv/bin/python scripts/run_dataset_collection.py \
  --release "$SHYN_RELEASE" \
  --execute \
  --max-cases 200 \
  --resume "$SHYN_JOURNAL"
```

Đây là lệnh resume journal v3 hiện có. Không dùng `--inherit-journal` thay cho resume: inherit tạo một journal mới và có thể lặp lại các ca đã thu sau mốc handoff 10 ca.

Controller bỏ qua scenario captured trong journal, giữ failed attempts, tự chạy soak mới, tự inject tuần tự, cleanup, export, đăng ký registry và tạo review packet. Lịch reference → validation → test, tối đa bốn ca/batch và Pod failure cuối batch. Sau Pod UID thay đổi phải soak lại. Không chạy nhiều fault song song.

`--max-cases` là số ca mới tối đa trong lần gọi, không phải số tổng đã thu. `--max-cases 200` cho phép hoàn tất phần còn lại của plan; không tạo 200 ca thêm ngoài plan.

### Tự chạy từng ca có quản lý

Chỉ khi controller cũ đã dừng an toàn:

```bash
caffeinate -di .venv/bin/python scripts/run_dataset_collection.py \
  --release "$SHYN_RELEASE" \
  --execute \
  --max-cases 1 \
  --resume "$SHYN_JOURNAL"
```

Khi kết thúc segment, kiểm journal/candidate rồi dùng lại lệnh để chạy ca tiếp theo. Dùng `--max-cases 4` nếu muốn tối đa bốn ca mới. Mỗi lần resume có thể phải soak lại; chạy liên tục tiết kiệm thời gian hơn. Không tắt terminal đang chạy controller.

Chỉ khi tạo một dòng collection mới có chủ đích mới dùng `--inherit-journal results/collection-releases/20261124-prospective-v3/predecessor-handoff.json`; đó không phải lệnh restart thường ngày.

## 6. Chạy trực tiếp một scenario tùy chọn

Cách này dành cho kiểm chứng có kiểm soát, không nên dùng để thay lịch 200 ca. Chạy trực tiếp không tự cập nhật collection journal và registry; nếu resume controller sau đó, controller chưa biết ca thủ công để bỏ qua.

Xem các scenario và split mà không đổi plan:

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path
for s in json.loads(Path('experiments/scenario-plan.json').read_text())['scenarios']:
 print(s['scenario_id'],s['split'],s['variant'],s['target'],s['parameters'],s['duration_seconds'],s['traffic_pause_seconds'])
PY
```

Chỉ render một manifest, chưa inject:

```bash
.venv/bin/python scripts/run_scenario.py --scenario-id S0009
```

Để kiểm toàn bộ manifest trên server mà chưa inject, khi không có controller/soak khác:

```bash
.venv/bin/python scripts/run_scenario.py --render-all --server-dry-run-all
```

Không bulk-apply thư mục manifest. Không chạy `experiments/generate_plan.py`/`make dataset-plan` trong cohort đã ghim nguồn.

Trước khi execute trực tiếp, chạy soak đủ 600 giây:

```bash
.venv/bin/python scripts/ensure_frontend_tunnel.py
caffeinate -di .venv/bin/python scripts/check_stability.py --seconds 600
```

Copy đúng đường dẫn `result.json` được in khi soak kết thúc. Chỉ dùng nếu `status=passed_short_soak`, UTC gate đạt, còn mới trong 15 phút và Pod UID/restart/manifest khớp. Ví dụ gán biến bằng đường dẫn thật của lượt vừa chạy; không dùng receipt cũ trong hướng dẫn:

```bash
export SHYN_RECEIPT="$PWD/results/stability/<timestamp-vua-chay>/result.json"
caffeinate -di .venv/bin/python scripts/run_scenario.py \
  --scenario-id S0009 \
  --execute \
  --stability-result "$SHYN_RECEIPT" \
  --collection-release "$SHYN_RELEASE"
```

Copy `path` mà runner trả về, không chọn một thư mục cũ cùng ID. Đăng ký attempt thủ công khi không có controller khác ghi registry:

```bash
export SHYN_CASE="/Users/cloudino/Documents/ChatGPT/shyn/data/candidates/<candidate-vua-chay>"
.venv/bin/python - <<'PY'
import os
from pathlib import Path
from scripts.run_dataset_collection import register
p=Path(os.environ['SHYN_CASE']).resolve()
g=register(p)
print(g['execution_status'],g['admission_status'])
PY
```

Lệnh trên tạo registry/handoff và quality/review packet nếu capture đạt; không admission và không đưa attempt vào collection journal. Muốn tính ca thủ công vào cùng cohort phải đối chiếu/ghép journal bằng quy trình có audit; không sửa journal bằng tay để tăng count. Vì vậy cách `--max-cases 1 --resume` ở mục 5 là lựa chọn phù hợp để tự thu đủ kế hoạch.

## 7. Kiểm tra sau mỗi ca

Với `SHYN_CASE` là đường dẫn tuyệt đối của ca vừa chạy:

```bash
.venv/bin/python - <<'PY'
import os,json
from pathlib import Path
p=Path(os.environ['SHYN_CASE']);g=json.loads((p/'ground-truth.json').read_text())
for k in ('execution_status','admission_status','error','cleanup_completed_at','cleanup_error','traffic_exit_code','recovery_issues','recovery_or_capture_error','observation_error','collector_after_error'):
 print(k,g.get(k))
for name in ('telemetry/capture.json','observation/telemetry/capture.json','quality-review.json'):
 f=p/name
 print(name,json.loads(f.read_text()) if f.exists() else 'MISSING')
PY
```

Điều kiện kỹ thuật cần có:

1. `execution_status=captured_requires_review`, không có error/cleanup_error/recovery_or_capture_error/observation_error.
2. `cleanup_completed_at` tồn tại; sau ca không còn chaos sở hữu bởi attempt.
3. Recovery issues rỗng, ứng dụng và monitoring Ready; không tăng node-local OOM hoặc lifecycle ở non-target. Pod failure được phép thay UID target.
4. Traffic có checkout thực và exit code 0. Lỗi request trong fault phải được giữ, có thể là tác động cần nghiên cứu; không đòi toàn bộ fault luôn zero lỗi.
5. Raw có metrics/logs/traces; không lỗi export hoặc cap/incomplete. Observation benchmark dài 60 giây quanh inject-confirmed, chỉ có span đã kết thúc trước cutoff, source hashes khớp.
6. Structural checks đều true. Vẫn cần người review xác nhận effect đúng target, recovery, relevance và near duplicate.
7. Collector/alert: kiểm `collector-window.json`, timestamp và lỗi collector nếu có. Không có alert không tự động đồng nghĩa case không có fault; phải báo detector miss. Collector chạy thành công không có nghĩa Gemini đã chẩn đoán.

Hồ sơ: `ground-truth.json`, `injection.yaml`, `chaos-status.json`, `warmup-state.json`, `recovery-state.json`, `traffic.json`, raw trong `telemetry/`, model input trong `observation/telemetry/`, `provenance.json`, `collection-release.json`, `quality-review.json`, `review-packet.json`. Network case có thêm counters/qdisc; không yêu cầu file này cho CPU.

Đọc raw toàn lượt để review effect và recovery. Chỉ dùng observation để benchmark B0–B3. Ground truth, chaos/qdisc và review packet không được đưa vào context hoặc KB.

## 8. Khi gặp lỗi

| Hiện tượng | Kiểm tra và xử lý |
|---|---|
| `Another ... active`, lock bận | Kiểm process, chờ lượt cũ kết thúc; không xóa lock hoặc chạy song song. |
| Tunnel 8080/8000 lỗi | Kiểm supervisor/Pod Ready; chạy lại đúng tunnel nếu tiến trình đã chết. Không deploy database vì lỗi port-forward. |
| Receipt hết hạn/UID đổi | Chạy soak 600 giây mới khi cluster đã sạch, không sửa timestamp receipt. |
| `stopped_requires_review` | Đọc journal error và ground truth của attempt cuối; xử lý nguyên nhân rồi resume. |
| Attempt còn `started` sau mất process | Kiểm cleanup/traffic/raw và đăng ký/reconcile có audit trước resume. Không tự coi là captured. |
| OOMKilled/Pod không Ready | `kubectl describe pod` và `kubectl logs --previous`; kiểm limits/node memory, giữ failed attempt. Thay source/env cần kiểm chứng và release/migration trước heldout. |
| Thiếu modality/cap/export incomplete | Không admission lượt đó. Kiểm Prom/Loki/Jaeger, retention, bounds và workload; giữ dữ liệu lỗi. |
| `Collection source changed` | Kiểm file nào khác hash. Khôi phục đúng source đã ghim hoặc tạo migration hợp lệ; không sửa hash để vượt gate. |
| API/quota/schema lỗi ở benchmark | Giữ execution/ledger, không ghi đè report hoặc tự retry. Report thiếu vẫn được giữ trong mẫu số test. |

Nếu còn chaos và controller đã thật sự dừng, xem resource cùng label:

```bash
kubectl --context=shyn-thesis -n sock-shop get stresschaos,networkchaos,podchaos --show-labels
kubectl --context=shyn-thesis -n sock-shop get -f "$SHYN_CASE/injection.yaml" -o yaml
```

Đối chiếu kind/name và label `thesis.shyn/attempt` với `injection.yaml` của đúng attempt. Chỉ nếu khớp ownership mới cleanup resource này:

```bash
kubectl --context=shyn-thesis -n sock-shop delete -f "$SHYN_CASE/injection.yaml" --wait=true --timeout=25s
```

Không `delete --all`, không xóa PVC, không `minikube delete`/prune volume. Việc cleanup muộn không biến attempt lỗi thành capture đạt; chạy attempt mới sau khi đủ điều kiện.

Nếu phải ngắt đột xuất, giữ terminal/log/journal. Tín hiệu dừng hoặc mất điện có thể để lại traffic/chaos; không mặc định đã cleanup. Chờ/kiểm đúng process `traffic/steady.py` của dự án kết thúc trước soak mới. Dừng cluster/database chỉ sau khi không còn thực nghiệm và đã có backup cần thiết.

## 9. Audit dataset và review

Chạy audit khi không có candidate mới đang được tạo/chưa đăng ký, ví dụ giữa batch hoặc sau khi controller kết thúc:

```bash
.venv/bin/python scripts/test_dataset.py
.venv/bin/python scripts/export_review_queue.py
```

Audit cần `errors=[]`; trạng thái `local_checks_passed_official_dataset_incomplete` chỉ xác nhận integrity local, không phải đủ 200. Nếu audit chạy đúng lúc controller chưa đăng ký candidate, kiểm lại sau checkpoint trước khi kết luận hỏng dữ liệu.

Reviewer vào `http://127.0.0.1:8501` → **Review dữ liệu**, tự xem raw/effect, điền danh tính/pseudonym, bốn check, reason, evidence location và relevance runbook. Không chọn approve hàng loạt nếu chưa đọc. Review năm KB runbook ở tab Runbook. Giữ nguyên source/KB đang ghim; review không tự reindex.

Reference/validation được review trong lúc thu. Nếu reviewer cũng là người tham gia đo, không xem ground truth test cho đến khi kết thúc cả phiên 14 nhiệm vụ. Xem RB16.

Khi controller đã kết thúc hoặc dừng an toàn, áp dụng review thật từng ca. Ví dụ preview trước:

```bash
.venv/bin/python scripts/apply_admission_review.py \
  --candidate "$SHYN_CASE" \
  --review "$PWD/results/review-handoff/prospective-review/$(basename "$SHYN_CASE").json"
```

Nếu preview đúng, thêm `--apply`. Tool khóa registry và từ chối khi collection đang ghi; không bỏ khóa. Với candidate đã admitted, không apply lại. Chỉ số count hợp lệ là các scenario unique đã admitted, không phải tổng số attempt.

## 10. Sau khi thu: kiểm tiếp những luồng nào

### A. Đủ dataset và cấu trúc

Phải đủ 200 scenario unique admitted, 120 reference/40 validation/40 test, ba lớp 67/67/66. Giữ attempt lỗi và phân bố detector miss/thiếu modality; không lấp thiếu bằng lượt lặp. Audit plan/provenance/source hash/near duplicate và hồ sơ reviewer phải khớp.

### B. Chuẩn bị benchmark local

Khi đủ observation của từng split, dùng journal v3:

```bash
.venv/bin/python scripts/prepare_prospective_benchmark.py \
  --journal "$SHYN_JOURNAL/journal.json" --split test
```

Validation tương tự `--split validation`; reference đang thu có thể dùng `--split reference --allow-partial`. Test/validation không cho partial. Tool tái dựng observation, tạo context, B0 và packet B1–B3; không gọi API. Manifest pending admission chưa được chấm test chính thức.

Output in đường dẫn manifest: `results/prospective-benchmark/<release-hash-prefix>/test/manifest.json`. Dùng đúng đường dẫn được in, không chọn manifest development cũ. Đặt biến `SHYN_MANIFEST` bằng đường dẫn tuyệt đối này.

### C. Kiểm request trước Gemini

Chọn một `approval_packet` từ manifest, resolve theo thư mục manifest rồi đặt `SHYN_PACKET` thành đường dẫn tuyệt đối:

```bash
.venv/bin/python scripts/run_approved_comparison.py --approved-packet "$SHYN_PACKET" --check-only
```

Phải có `packet_valid=true`, `api_called=false`. Trước chạy thật, xem request-manifest, context ba mode, embedding query, allowed runbooks và ngân sách. Mỗi packet tối đa ba generation và hai query embedding, không retry/reindex; 40 test packet tối đa 120 generation/80 query embedding trước cache. Đây là số request, không phải trần hóa đơn. Các phạm vi Gemini cũ đã dùng hết.

Khi chính bạn quyết định thực thi một packet đã kiểm và chấp nhận gửi dữ liệu/chi phí:

```bash
.venv/bin/python scripts/run_approved_comparison.py --approved-packet "$SHYN_PACKET"
```

Lệnh này gọi Google Gemini và có thể tính phí. `execution.json` ngăn chạy lại im lặng; lỗi giữ nguyên. Không xóa execution để retry. Không dùng model/KB/prompt khác giữa các ca test. B0–B3 dùng cùng context gốc nhưng B1/B2 chỉ giữ log theo thiết kế ablation.

### D. Đo người trước review test

Sau khi đủ test context và report B3 cho các nhiệm vụ đã đăng ký, người tham gia tự làm 14 nhiệm vụ tại tab **Đo thời gian**. Không để trợ lý bấm thay, không xem ground truth hoặc report ngoài điều kiện được giao. Thời gian đo là quyết định trên context/report tải sẵn, không phải live TTD. Xem RB16 để tổng hợp số đo thực tế.

### E. Review test, admission và readiness

Sau phiên đo, reviewer mới mở đáp án test, hoàn tất review/admission. Chạy lại prepare benchmark để refresh admission metadata trong manifest; context/packet giữ nguyên. Sau đó:

```bash
.venv/bin/python scripts/check_benchmark_readiness.py
```

Exit 2/`not_ready` là còn blocker. Đọc từng blocker về 200 admitted, split, provenance, protocol/freeze và KB review. Không đổi pending/draft sang approved/frozen để vượt check. Collection release là precommitment thu dữ liệu, không tự xác nhận toàn bộ điều kiện nghiệm thu. Nếu hồ sơ freeze cũ khác cohort v3, phải đối chiếu và lập hồ sơ tương thích có audit trước công bố benchmark; không âm thầm cập nhật hash sau khi xem kết quả test.

### F. Chấm và phân tích

Khi đủ điều kiện chính thức và manifest là test đã admitted:

```bash
.venv/bin/python experiments/evaluate.py "$SHYN_MANIFEST" --output results/evaluation/official-test-b0-b3.json
.venv/bin/python scripts/score_retrieval.py "$SHYN_MANIFEST" --output results/evaluation/official-test-retrieval.json
```

Chỉ số cần báo: Top1/Top3 đúng target hoặc directed edge và đúng class; coverage/API failures; khoảng tin cậy và tương quan theo họ; Recall@3/MRR@3 từ relevance thật; grounding/hallucination chấm claim/raw riêng; latency replay, live detector/collector và human time tách riêng; token/cost estimate khác hóa đơn. Giữ lỗi nền queue-master và phân tích thay vì xóa để tăng accuracy. Nếu chỉ một người review, công bố giới hạn; không bịa agreement hai người.

Output retrieval refuse overwrite; chọn tên mới khi phân tích lại. Scorer accuracy cần output phiên bản riêng để bảo toàn kết quả trước.

### G. Kiểm demo và bàn giao

Kiểm chuỗi live telemetry → alert → collector → context → report khi có phạm vi API, cùng phương án replay dùng report đã có. Không inject demo mới trong khi cohort đang thu. Sau thay code chạy `make test` phù hợp; khi chỉ có thêm data thì audit data, không coi rerun unit tests là review effect.

Bộ nộp: source/config/lockfile, hướng dẫn chạy, plan/split, raw/observation/provenance, quyết định admission/review, manifest/report/ledger, bảng kết quả và failure analysis, số đo người thật, giới hạn ARM64/AMD64 và segment collector, demo/replay và bản báo cáo. Loại `.env`, API key, kubeconfig, credentials, SQLite/DB backup và dữ liệu không cần thiết khỏi gói phân phối. Không gửi reviewer mapping/test answers cho người tham gia trước phiên đo.

## 11. Thứ tự thao tác ngắn nhất

1. Đọc trạng thái: nếu controller đang running thì để chạy.
2. Kiểm tunnel và review reference/validation song song.
3. Khi dừng lỗi: kiểm cause/cleanup, xử lý rồi resume cùng journal.
4. Thu đủ 200 setting; audit raw/observation/provenance.
5. Chuẩn bị test packet local, kiểm và quyết định phạm vi Gemini.
6. Chạy B0–B3, người tham gia đo 14 nhiệm vụ trước đáp án test.
7. Review test/runbook/claim, apply admission khi không còn controller ghi registry.
8. Refresh manifest, hoàn tất readiness/freeze đối chiếu, chấm và viết kết quả.
9. Diễn tập live/replay và kiểm gói nộp không chứa secrets.
