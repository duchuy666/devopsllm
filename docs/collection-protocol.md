# Cập nhật triển khai prospective ngày23/11

Người dùng xác nhận bản cuối bắt buộc200ca và có một reviewer độc lập. Quy trình đang thực thi: [RB15](runbooks/RB-15-prospective-collection.md), cấu hình `config/collection-protocol.yaml`, release `results/collection-releases/20261123-prospective-v1/release.json`. Cửa sổ offline30giây trước/sau xác nhậninject đã precommit; không suy ra liveTTD. Admission yêu cầu reviewer độc lập thực tế; review claim theo rubric hai người vẫn cần phiếu riêng.

Phần dưới là ứng viên quy trình trước khi chốt release, được giữ cho lịch sử; những điểm cutoff còn chờ ở đó đã được chốt cho đợt prospective này, không hồi tố vào pilot cũ.

# Collection protocol — ứng viên để review

Ngày23/11/2026. Trạng thái **candidate_not_frozen**. Giữ nguyên split/plan200case, không mở held-out test khi còn hiệu chỉnh. Không tự admission các pilot.

## Chuẩn bị và thứ tự

1. Cắm nguồn Mac, giữ máy thức; DockerVM8GiB, Minikube7GiB/4CPU. Kiểm canonical manifest/image lock, native Go và các policy Mongo/MySQL/frontend đang active. Backup database trước mọi restart có thể mất dữ liệu.
2. Kiểm cả14Pod app và monitoring/chaos Ready, không lỗi chồng; mở tunnel8080/8000/9090/3100/16686. HTTP200 frontend trước traffic. Soak600giây đạt cả health gate và UTC gate; receipt hết hạn sau15phút hoặc khi manifest/PodUID/restart thay đổi.
3. Chỉ chạy1–4scenario reference tuần tự qua runner; Pod failure đặt cuối. Không build/deploy/soak đồng thời. Giữ nguyên plan/group/seed/target/intensity đã định, không thay setting sau khi nhìn kết quả để biến thất bại thành thành công.
4. Warmup30giây phải có checkout và0lỗi, lifecycle ổn định. Lưu preflight và warmup. Inject có ownership label, chờ controller AllInjected tối đa20lần×2giây; timeout create vẫn kiểm cleanup đúng resource, không mặc định chưa tạo.
5. Trong fault lưu cgroup khoảng5giây, dừng nếu node-local OOM tăng hoặc PSI full avg10>5. Resource/network theo duration trong plan; Pod kill quan sát30giây. Lưu qdisc riêng ngoài observation.
6. Cleanup resource đúng ownership, chờ recovery tối thiểu35giây, traffic và telemetry export phải lưu cả lỗi. Không chạy tiếp nếu cleanup/health/restore chưa xác nhận.
7. Lưu raw, query/time window, export limits, capture flag, image/config/source hash, trigger timestamps. Quality review không tự sửa admission. So sánh before/fault/recovery và collateral impact.

## Tách hai loại cửa sổ

Raw toàn lượt từ trước inject tới recovery phục vụ **kiểm chứng tác động và chất lượng thu thập**. Không mặc định dùng toàn cửa sổ này để báo live TTD: nó có thể chứa quan sát sau cleanup.

Collector phát triển hiện dùng120giây trước trigger và30giây sau trigger. Chọn cutoff benchmark phải chốt trên reference/validation trước freeze, giữ cùng observation cutoff giữa B0–B3. Detector miss cần được ghi riêng; không tự loại một fault có thật. Chính sách observation thay thế khi detector miss và các case thiếu modality còn cần chốt bằng reference calibration; chưa dùng test để lựa chọn.

Context0.4.1 chỉ đọc metrics/logs/traces; không đọc đường dẫn fault, ground truth, chaos status, qdisc hoặc nhãn target. ID phụ thuộc payload/config thực tế. Ground truth và quality review dành cho scorer/reviewer. Prompt0.2 và selection mới chưa có LLM evaluation.

## Admission và review

Giữ execution/technical effect/independent admission thành các trạng thái riêng. Failed inject, effect không đủ, telemetry thiếu/cap, detector miss, API/schema lỗi phải có lý do và số lượng. Những trường hợp này không được âm thầm bỏ khỏi thống kê.

Hai người chấm độc lập kiểm target/effect/recovery, provenance và near duplicate. Cùng fault/variant/target luôn cùng split; exact hash không đủ kiểm near duplicate. Reviewer ghi danh tính hoặc pseudonym, thời điểm, quyết định, lý do và vị trí bằng chứng. Không điền giả kết quả review hay thời gian người dùng.

## Điều kiện mở validation/test

Chốt observation cutoff/missing-source policy; thực nghiệm reference đủ target/intensity; protocol/threshold/context/prompt/B0/KB/model/retry/token/traffic/environment được pin bằng hash. Validation phục vụ hiệu chỉnh; test chỉ chạy khi freeze và không index vào KB. Thay pipeline sau xem test phải khai báo và dùng test độc lập mới nếu muốn kết luận tổng quát.

Benchmark B0–B3 dùng cùng case/cutoff; đúng phải khớp service hoặc directed edge và fault class. Giữ API errors/missing reports trong mẫu số đã khai báo. Chấm claim và retrieval relevance độc lập; live latency, replay latency và thời gian người dùng báo riêng. Chi phí estimate khác hóa đơn, không suy ra ROI khi chưa đo người thật.

## Bằng chứng hiện có và phần chưa đạt

Plan200/28group,67/67/66,split120/40/40;8attempt/7capture development trước pipeline mới,official0. Ba nguồn collector mới và frontend4peer đã kiểm chứng; chuẩn bị chạy lại network calibration với context mới sau soak. Chưa có200case admitted, human review, relevance labels hoặc official test accuracy.
