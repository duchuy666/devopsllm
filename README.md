# Trợ lý chẩn đoán sự cố DevOps dùng LLM và RAG

**Cài đặt và chạy: xem [HUONG-DAN-CHAY.md](HUONG-DAN-CHAY.md).**

Triển khai theo báo cáo khóa luận: Sock Shop trên Minikube, ba nhóm lỗi Chaos Mesh, telemetry log–metric–trace, FastAPI, Drain3, Qdrant, LangChain và Streamlit. LLM chuyển sang Gemini API theo yêu cầu ngày 20/11/2026; xem `docs/decisions.md`.

Máy phát triển: MacBook Air M2, RAM 16 GB, SSD 256 GB. Docker VM dùng 8 GiB RAM; Minikube đã tăng từ 6 lên 7 GiB sau khi đo memory pressure tại cgroup. Cấu hình phải được kiểm chứng bằng pilot.

## Trạng thái hiện tại

Sock Shop, telemetry đa nguồn, Chaos Mesh, collector, Qdrant và Streamlit đã chạy. So sánh Gemini trên cùng CPU pilot đã chạy: B1/B2 chọn nhiễu queue-master, B3 đúng payment / Resource Exhaustion Top-1. Đây là một ca development, chưa là benchmark chính thức. Có 9 lần thử pilot, 5 ca có tác động; **0/200 case chính thức**. Bộ 200 scenario đã lập kế hoạch, chưa phải dataset.

Testbed đã gặp OOM user/payment và probe timeout qua thời gian chạy dài; hai soak đầu có checkout lỗi. Đã tăng RAM node và tài nguyên catalogue; soak cuối 5 phút đạt 169/169 checkout, không request lỗi. Chưa xác minh ổn định dài hạn, freeze hoặc chạy batch. Xem [tiến độ](docs/progress/STATUS.md), [review pilot](docs/progress/PILOT-REVIEW.md).

## Bắt đầu và vận hành

Đọc [luồng build từng bước](docs/BUILD-FLOW.md) và [11 runbook vận hành](docs/runbooks/README.md). Đã có 5 runbook tri thức phủ CPU, memory, network delay, packet loss, Pod failure; vẫn cần review/validation.

UI: http://127.0.0.1:8501. Sock Shop: http://127.0.0.1:8080. Để mở lại môi trường, dùng RB08. Tab Report đã lưu xem kết quả cũ không gọi thêm API; nút chẩn đoán gửi dữ liệu tới Gemini.

`make test`: kiểm tra xử lý dữ liệu/scorer. `make dataset-plan`: chỉ tạo scenario plan. `make stability`: soak 5 phút, không chạy cùng chaos. `make evaluate-pilot`: chấm offline một ca development, không phải accuracy trên tập test.

## Các mốc

- M0: công cụ, Docker engine và image tương thích.
- M1: Sock Shop và traffic ổn định.
- M2: có log, metric, trace và alert webhook.
- M3: ba kịch bản chaos, collector và ground truth.
- M4: LLM report, RAG và giao diện.
- M5: pilot, khoảng 200 case, freeze và benchmark B0–B3.
- M6: phân tích sai số, thời gian, chi phí và hồ sơ tái lập.

Kết quả so sánh: [CPU B1–B3](docs/progress/CPU-COMPARISON.md). Ba generation mới có paid-standard estimate tổng 0,02257125 USD, chưa gồm embedding hoặc đối chiếu hóa đơn.

Ngày22/11: thêm scenario runner và3serviceGoARM64 thử nghiệm; user cócompatibilitypatchJSONhrefđược ghi provenance. Xem [RB09](docs/runbooks/RB-09-scenario-runner.md), [RB10](docs/runbooks/RB-10-native-go.md). Context builderv0.3 giữusage/limit theoPod; chưa gọi thêmGemini.

Mốc mới: [runner/native/shipping comparison](docs/progress/SHIPPING-RUNNER-COMPARISON.md). Soak 10 phút đạt 327 checkout không lỗi; S0011 đã capture/recovery và B3 chẩn đoán đúng shipping. Đây là calibration, chưa là dataset/test chính thức.

Đợt tiếp theo: [reference calibration](docs/progress/REFERENCE-CALIBRATION.md) đã chạy memory, delay, loss và Pod failure; cùng CPU trước đó đủ 5 biến thể được kiểm chứng tác động ở mức phát triển. Soak mới 336 checkout không lỗi; official admitted vẫn 0/200; không gọi thêm Gemini.

Mới nhất: [detector mạng](docs/progress/NETWORK-DETECTOR-VALIDATION.md) đã được bổ sung và xác minh live qua hai ca chạy lại; [kiểm thử dataset](docs/progress/DATASET-VALIDATION.md) đạt audit local và server dry-run 200/200 manifest. Có 8 attempt/7 lượt capture, không tự admission; 30 Python test và promtool tests đạt.

Giao diện tại http://127.0.0.1:8501 có 6 tab và B0 local; hiện 40 Python test đạt và 19 report Gemini đã lưu. MongoDB đã có cache hook sau startup, qua backup/restore và checkout; fresh soak sau cutover còn pending. Catalogue-db vừa có thêm OOM nên chưa chốt ổn định dài hạn. Xem [bàn giao sản phẩm](docs/progress/PRODUCT-HANDOFF.md) và [cache persistence](docs/progress/DB-CACHE-PERSISTENCE.md).
