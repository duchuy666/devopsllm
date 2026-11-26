# RB 06 Thu và kiểm soát dataset

## Trạng thái

`experiments/scenario-plan.json` đã lập 200 scenario, 28 nhóm, phân bổ 67/67/66 và split 120/40/40. Đây chỉ là kế hoạch, official admitted = 0. Tạo lại bằng `make dataset-plan`; không tạo lại plan giữa các lượt thu để thay đổi split. Runner mới scripts/run_scenario.py dựng đủ target/parameter của plan, có single-reference execution và preflight/receipt/cleanup; helper chạy batch nhỏ tối đa 4 reference case, chưa admission. Xem RB09. Script pilot cũ vẫn dùng target cố định.

Chưa chạy batch 200 case. Chỉ có dữ liệu development pilot. Không đổi tên pilot lỗi hoặc mẫu không có tác động thành case thành công.

## Kiểm thử dataset

```bash
make dataset-test
make scenario-validate-all
```

Lệnh đầu kiểm local: plan count/group/split/leakage, registry đối chiếu scenario/seed/target/parameters, execution/admission consistency, raw JSON và structural checks cho captured case, provenance checksum nếu có, exact telemetry duplicates giữa split. Failed attempt được giữ nhưng không tính captured/admitted; attempt chưa đăng ký là lỗi audit. Không gọi Gemini hoặc tự admission.

Lệnh sau đọc topology thật và gửi **server dry-run từng manifest của cả 200 scenario**, không tiêm lỗi. Kết quả mỗi dòng ở `.runtime/scenario-manifests/<run>/manifest-index.json`. Chạy tách khỏi soak/chaos vì cùng dùng experiment lock. Dry-run đạt không chứng minh hiệu ứng thực tế trên mọi target/intensity.

Kết quả local ở `results/evaluation/dataset-validation.json` luôn ghi `official_admitted`, `remaining_official` và giới hạn kiểm tra. Exact hash không phát hiện mọi semantic near duplicate; independent human review và observation protocol vẫn cần trước admission/test benchmark.

## Điều kiện trước batch

Pilot phải đi được toàn bộ từ chaos, alert, context, RAG đến báo cáo Gemini có bằng chứng. Chốt schema, resource budget, traffic, cửa sổ dữ liệu, tracing coverage và quy tắc chất lượng trước khi mở rộng. Cấu hình hiện tại trong `config/experiment-protocol.yaml` vẫn draft. Quy trình ứng viên mới ở [collection protocol](../collection-protocol.md), phân biệt rõ raw toàn lượt với observation cutoff để chẩn đoán.

## Chuẩn bị scenario manifest

Mỗi bản ghi gồm scenario_id, scenario_group_id, fault class/variant, service hoặc directed edge, intensity, duration, traffic profile, seed và môi trường. Lập khoảng 200 bản ghi gần cân bằng 67/67/66. Đa dạng target/parameter; không chỉ đổi ID hoặc timestamp.

## Thu tuần tự

Kiểm tra healthy, warm-up, lưu baseline, inject, xác nhận target thực, lưu ground truth, quan sát, cleanup, xác nhận recovery và xuất telemetry. Một thời điểm chỉ một lỗi. Tạm dừng batch khi cleanup hoặc node health lỗi; không chạy chồng để đạt số lượng.

## Chất lượng và admission

Phân loại riêng inject thất bại, inject nhưng không quan sát thấy tác động, thiếu telemetry, detector bỏ sót và report lỗi. Detector bỏ sót không phải lý do loại một failure case thực. Lưu trường hợp lỗi để tính coverage và threat to validity.

Kiểm tra cờ export log/trace incomplete, timestamp, evidence target, mức nhiễu testbed và recovery. Review trước khi đánh dấu valid. Ground truth và chaos metadata luôn lưu ngoài thư mục context.

## Chia tập

Chia theo scenario group và near duplicate, mục tiêu 120 reference, 40 validation, 40 test. Giữ ba nhóm lỗi trong mỗi tập. Nếu kích thước group khiến không thể đạt chính xác mục tiêu, điều chỉnh group hoặc công bố phân bố thực; không phá nhóm để ép số lượng.

Tạo split manifest cố định, source hash và phiên bản. Qdrant chỉ chứa tri thức được duyệt và reference cases; cấm test hoặc case gần trùng test. Test case không được thêm vào operational memory trước khi toàn bộ test hoàn tất.

## Review split kế hoạch v0.2

Audit ban đầu tìm thấy 9 chữ ký fault/variant/target ở nhiều split do nhóm trước đó có cả traffic profile. Bản v0.2 gom cùng chữ ký vào một split bất kể traffic/intensity/duration/seed; còn 28 nhóm, giữ đúng 67/67/66 và 120/40/40, đủ biến thể trong từng split. Chạy `experiments/audit_plan.py` để kiểm tra lại. Không coi zero structural risk là chứng minh không có near duplicate trong log/trace thật. Pod-kill có nhiều lượt lặp cùng setting để đo biến thiên; công bố là replication, không gọi 200 ca là 200 cấu hình lỗi độc nhất.

## Kiểm tra trước benchmark chính thức

`make benchmark-check` kiểm riêng đủ admission/count/split, provenance, hồ sơ reviewer, protocol/freeze, source hash và review KB. Hiện trả not_ready với exit code2; audit local đạt không làm benchmark tự sẵn sàng. Xem [RB14](RB-14-benchmark-readiness.md).
