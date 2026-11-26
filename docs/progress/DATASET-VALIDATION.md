# Kiểm thử dataset ngày 22/11/2026

Kết quả: kiểm tra local và server dry-run đạt; dataset thực nghiệm chính thức chưa hoàn tất. Không có dữ liệu giả hoặc tự admission để lấp phần còn thiếu.

## Scenario plan

200 ID duy nhất, 28 nhóm; không có chữ ký fault/variant/target hoặc group vượt split. Có đủ biến thể trong từng nhóm lỗi và từng split.

| Nhóm lỗi | Reference | Validation | Test | Tổng |
|---|---:|---:|---:|---:|
| Resource Exhaustion | 40 | 13 | 14 | 67 |
| Network Delay / Packet Loss | 40 | 14 | 13 | 67 |
| Pod Failure | 40 | 13 | 13 | 66 |
| Tổng | 120 | 40 | 40 | 200 |

Biến thể: 35 memory, 32 CPU, 34 loss, 33 delay, 66 Pod failure. Cả **200 manifest** được dựng từ topology thật và gửi server dry-run thành công, không có injection trong bước này. Dry-run không xác minh hiệu ứng thực tế trên mọi target/intensity.

## Dữ liệu đã thu qua runner mới

Registry có **8 attempt**, gồm 1 preflight failed và **7 lượt capture**: CPU 1, memory 1, delay 2, loss 2, Pod failure 1. S0078/S0071 được chạy lặp sau khi bổ sung detector, vẫn cùng reference scenario; không gọi thành 7 cấu hình lỗi độc nhất. Legacy pilots nằm riêng, chưa gộp vào registry này.

Đã kiểm tra:

- Registry khớp plan về scenario/group/split, target, parameters, duration và seed; execution/admission/effect status khớp hồ sơ.
- Bảy lượt capture có raw JSON và đều đạt structural checks, technical effect review; independent human review pending.
- Không có exact telemetry file duplicate vượt split trong dữ liệu hiện có. Tất cả candidate hiện là reference; chưa có collected validation/test để đánh giá observed leakage giữa ba tập.
- Provenance checksum đạt ở 6 candidate mới có snapshot. CPU shipping cũ thiếu source snapshot kiểu mới, được báo là legacy, không che giấu hoặc dựng lại bằng mã hiện tại.
- Failed attempt không được tính captured/admitted; registry không có attempt chưa đăng ký; số official nhất quán.

**Official admitted 0/200; còn thiếu 200 ca được admission.** Không có official test accuracy, semantic near-duplicate clearance hoặc kết quả human baseline trong lần kiểm tra này. Exact file hashes không đủ phát hiện mọi near duplicate.

## Kiểm thử phần mềm và cách chạy lại

30 Python unit test đạt, gồm negative tests cho plan leakage, admission sai của preflight failure, registry/plan mismatch và attempt chưa đăng ký. Promtool rule tests đạt, xem [detector validation](NETWORK-DETECTOR-VALIDATION.md).

```bash
make test
make dataset-test
make scenario-validate-all
make alert-test
```

`dataset-test` chỉ kiểm local và không gọi cloud; `scenario-validate-all` cần cluster và chỉ server dry-run; `alert-test` dùng promtool của Pod hiện có, không deploy rule. Chạy các bước cần experiment lock ngoài lúc soak/chaos.

Kết quả máy đọc: `results/evaluation/dataset-validation.json`, `results/detector-validation/dataset-server-dry-run.json`, `results/detector-validation/python-tests.log`. Ground truth/review/provenance không phải dữ liệu đầu vào LLM. Không gọi thêm Gemini trong đợt này.
