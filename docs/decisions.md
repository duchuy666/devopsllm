# Quyết định triển khai

## Chuyển provider sang Gemini

Ngày 20/11/2026, người dùng yêu cầu chuyển từ OpenAI trong báo cáo sang Gemini API. Giữ Sock Shop, ba fault class, Qdrant, LangChain, Streamlit và protocol đánh giá; thay adapter LLM, embedding provider và bảng giá.

Model ứng viên: `gemini-3.8-flash`, stable theo https://aistudio.google.com/docs/models/gemini-3.8-flash. Embedding text ứng viên: `gemini-embedding-001`, vẫn có theo https://aistudio.google.com/docs/embeddings. Phải xác nhận quyền truy cập thực tế bằng API key của người dùng trước khi freeze thực nghiệm. Không dùng alias `latest` hoặc thay model giữa các baseline.

Ghi model version trả về, thời gian gọi, prompt/config, usage metadata, thinking tokens và bảng giá đúng ngày chạy. Chi phí embedding tách riêng; không báo số 0 nếu chưa cấu hình giá. Cấu hình ban đầu giới hạn một request mỗi run để kiểm tra kết nối trước khi chạy benchmark hàng loạt.

Gemini API key được lưu trong `.env` gitignored, không trong Markdown, manifest, log, URL hoặc image. Chưa có key thì không gọi API và không sinh chẩn đoán giả. Nội dung báo cáo Word gốc được giữ nguyên; thay đổi này cần phản ánh trong bản khóa luận cập nhật.

## Sock Shop trên M2

11/14 image upstream thiếu ARM64. Payment preflight và checkout thực tế chạy thành công qua lớp giả lập sẵn trong Docker VM. Cấu hình triển khai hiện tại trộn ARM64 và AMD64 giả lập; phải công bố giới hạn này khi phân tích CPU, latency và external validity.

## Bộ điều khiển chaos

Chaos Mesh 2.8.8 namespaced thiếu quyền đọc cache RemoteCluster ở cấp cluster trong môi trường này, làm controller restart và pilot đầu không inject được. Namespace annotation filter cũng cần quyền đọc namespace metadata. Bổ sung ClusterRole chỉ có get/list/watch đối với RemoteCluster và Namespace. Không mở rộng quyền inject ra ngoài sock-shop.

## Hiệu chỉnh testbed sau pilot ngày 20/11/2026

Một controller Chaos Mesh duy nhất được tắt leader election sau các lần mất lease trên node chậm. Webhook và phạm vi namespace giữ nguyên.

Kubelet ghi user OOMKilled lúc 14:23:24 UTC ngoài chaos; limit được tăng từ 200Mi lên 384Mi. Các HTTP readiness probe dùng timeout 3s, period 5s; liveness timeout 3s, period 10s, failureThreshold 6 để giảm restart do node chậm ngắn hạn. Đây là cấu hình development mới, không ghi đè điều kiện của pilot cũ và chưa chứng minh ổn định dài hạn. Cần baseline/soak trước freeze dataset.

## Điều chỉnh RAM node dựa trên cgroup

Ngày 21/11 giờ Việt Nam (23:48 UTC ngày 20/11), memory.current sát memory.max=6442450944; memory.events max=30980098, oom_kill=12 tích lũy; PSI full avg60=14,83%. VM vẫn có MemAvailable nên Node MemoryPressure=False chưa phản ánh giới hạn riêng của container Minikube. Tăng node cap từ 6GiB lên 7GiB trong VM 8GiB, không tăng VM, không xóa cluster/PVC. Giữ swap container tắt. Start script/config được đồng bộ; cần soak mới trước thu dataset. Bằng chứng trước sửa: `results/environment/node-cgroup-before-memory-adjustment.txt`.

## Tài nguyên catalogue sau soak thứ hai

Sau tăng RAM node, catalogue vẫn mất Ready trong healthy checkout; metric chạm CPU ~0,2 core và memory ~198MiB trên cap 200m/200Mi. Liveness restart xảy ra, log có Zipkin timeout. Đây là tương quan tài nguyên/timeout, chưa chứng minh nguyên nhân GC hoặc memory leak. Điều chỉnh development catalogue thành 500m/384Mi rồi chạy soak mới; không thay image hoặc tắt tracing. Payment giữ limit 200m/200Mi để không âm thầm đổi pilot definition; OOM payment qua thời gian dài vẫn cần xử lý/đánh giá trước batch.
