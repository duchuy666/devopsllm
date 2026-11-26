# Danh mục runbook

Có **17 runbook vận hành** và **5 runbook tri thức**. Số runbook không phải số incident: official dataset hiện 0/200; 200 scenario trong plan chưa được thực thi đầy đủ.

| Thứ tự | Runbook | Chuẩn bị/đầu ra |
|---|---|---|
| 1 | [Môi trường](RB-01-environment.md) | Docker, CPU/RAM/đĩa, versions, doctor |
| 2 | [Testbed](RB-02-testbed.md) | Image digest, manifest, rollout, checkout |
| 3 | [Observability](RB-03-observability.md) | Ba nguồn telemetry, trace liên service, alert/collector |
| 4 | [Chaos pilot](RB-04-chaos-pilot.md) | Tiêm tuần tự, xác minh tác động, cleanup/recovery |
| 5 | [Gemini và RAG](RB-05-gemini-rag.md) | Key local, model, index, context review, report/usage |
| 6 | [Dataset](RB-06-dataset.md) | Scenario plan, admission, grouped split, chống leakage |
| 7 | [Benchmark](RB-07-benchmark.md) | Freeze, B0–B3, scorer, rubric, đo thời gian |
| 8 | [Demo/phục hồi](RB-08-demo-recovery.md) | Các URL, khởi động/dừng, replay, khắc phục |
| 9 | [Scenario runner](RB-09-scenario-runner.md) | Dựng manifest, preflight/receipt, chạy từng candidate và cleanup |
| 10 | [Go ARM64 native](RB-10-native-go.md) | Source/dependency pin, compatibility patch, migration và rollback |
| 11 | [Cache MongoDB sau restart](RB-11-db-cache-persistence.md) | Backup/restore cô lập, cutover có quiesce, postStart/readback và phục hồi |
| 12 | [MySQL memory](RB-12-mysql-memory.md) | Config startup, backup/restore/checksum/account, cutover và timing gate |

| 13 | [Frontend tracing](RB-13-frontend-tracing.md) | Fixture Node4.8, live B3/peer, collector0.3, context selection và rollback |

| 14 | [Benchmark readiness](RB-14-benchmark-readiness.md) | Admission, provenance, split/count, review và hash trước benchmark |

| 15 | [Prospective collection](RB-15-prospective-collection.md) | Release ghim nguồn, 200 ca, observation cố định, review và admission có transaction |

| 16 | [Đo thời gian ẩn đáp án](RB-16-blind-human-timing.md) | Người tham gia thật, 14 nhiệm vụ, giữ ẩn test và phân tích giờ công có điều kiện |

| 17 | [Tự chạy và kiểm đầu ra](RB-17-self-run-and-acceptance.md) | Theo dõi, resume, chạy từng ca, kiểm lỗi và toàn bộ luồng sau collection |
| 18 | [Đáp ứng đề cương](RB-18-proposal-conformance.md) | Case memory, live TTD alert→report, Grafana dashboard, nhãn expected_evidence/runbook_id |

Tri thức ở `knowledge/runbooks/`: CPU, memory, network delay, packet loss, Pod failure. Đủ phủ 5 biến thể thuộc 3 nhóm đề tài; chưa được validated chỉ dựa vào số lượng. Không cần 200 runbook; cần 200 case thực nghiệm cùng bằng chứng chất lượng.

Runner mới đã kiểm chứng tác động phát triển cho 5 biến thể qua live execution, xem [calibration](../progress/REFERENCE-CALIBRATION.md). Điểm cần hoàn thiện trước nghiệm thu: ổn định dài hạn trên testbed 7GiB, detector/trace coverage, admission 200 case, B0 ranking, benchmark B1/B2/B3 trên test độc lập, rubric/relevance labels và đo thời gian người dùng. Các file hướng dẫn đã có không đồng nghĩa những bước này đã chạy.
