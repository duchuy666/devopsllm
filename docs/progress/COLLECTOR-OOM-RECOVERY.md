# Khôi phục collector và tiếp tục collection

Ngày 24/11/2026, tiếp tục theo yêu cầu hoàn thiện sớm nhất có thể. Không giảm mục tiêu 200 ca hoặc tự tạo review.

S0009 ở lượt `CANDIDATE-20261123T124106647408-S0009` tiêm CPU shipping và cleanup lúc 12:42:25 UTC ngày 23/11. Raw đã xuất, nhưng recovery ghi collector không Ready; Kubernetes xác nhận collector OOMKilled lúc 12:43:54 UTC, giới hạn cũ 192 MiB. Lượt này không có observation được chứng nhận và không tính vào 200. Ground truth, raw và registry được giữ nguyên; không gán lại thành capture đạt.

## Thay đổi đã thực hiện

Collector 0.3.1 chỉ xử lý một job capture tại một thời điểm; ba nguồn trong một job vẫn truy vấn song song. Cutoff luôn là thời điểm trigger gốc, không dời theo lúc job bắt đầu xử lý. Payload được ghi JSON theo luồng; future chỉ trả metadata để tránh giữ ba payload lớn trong parent. Giới hạn RAM tăng lên 512 MiB, request 128 MiB; CPU không đổi.

Đã backup SQLite bằng API backup online trước rollout và kiểm tra không còn capture active tại thời điểm triển khai. Không restart database Sock Shop. Image, deployment trước/sau và backup được giữ local; không đưa SQLite hoặc thông tin môi trường vào context gửi mô hình.

## Kiểm chứng

Ba manual development capture mới đều đạt đủ nguồn, không restart hoặc thay Pod UID giữa phiên; RAM cgroup peak cao nhất 108,76 MiB. Đây là probe phát triển ngắn, không chứng minh mọi cửa sổ tương lai sẽ nằm dưới giới hạn. Một probe đầu bị reset kết nối do tunnel chuyển Pod sau rollout được giữ là failed; probe thứ hai có output riêng.

97 kiểm thử Python đạt, gồm ba kiểm tra semaphore/persist và một kiểm tra giữ provenance qua nhiều release. Giao diện có cảnh báo khi controller dừng và tiến độ tự đọc journal mỗi 15 giây; không gọi Gemini khi cập nhật.

## Release và tiếp tục

V3 ghim 50 file tại `results/collection-releases/20261124-prospective-v3/release.json`. Giữ nguyên plan 0.3, observation ±30 giây/completed span, model, prompt, context, B0, KB và mã telemetry query. Mười reference capture được chuyển tiếp nguyên setting với release hash từng ca; chưa mở validation/test. Hai file nguồn chung thay đổi là packager và controller để hỗ trợ provenance nhiều cấp; thêm sáu pin cho collector/deploy.

Dịch vụ hỗ trợ đã đổi cấu hình nên cần công bố segment môi trường trong phân tích. Bảy capture đầu có provenance v1, ba capture sau v2; các lượt mới dùng v3. Không diễn giải các segment như cùng điều kiện hạ tầng hoàn toàn.

Đã khởi chạy soak 600 giây sau rollout. Collection v3 chỉ được bắt đầu khi receipt này đạt và proof ba capture manual đạt. Lượt S0009 cũ được giữ là thất bại; collector sẽ tạo thư mục attempt mới, sau đó tiếp tục schedule tuần tự. Không retry tự động nếu lượt mới hoặc health gate thất bại. Admission và quyền gọi Gemini vẫn là các mốc riêng.

Hồ sơ kiểm chứng nằm tại `results/collector-oom-recovery/20261124T154439Z`, rollout ở `results/collector-rollout/20261124T154502Z`, migration ở release v3. Không phân phối backup SQLite như một phần gói source.

Soak `20261124T154551Z` đã đạt 600 giây, UTC gate đạt, 318 checkout/0 request lỗi. Journal v3 đang hoạt động: `results/dataset-collection/20261124T155554Z/journal.json`. Số capture/admission hiện tại phải đọc từ journal/registry; khởi chạy không đồng nghĩa hoàn tất.
