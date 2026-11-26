# Kiểm chứng lỗi mạng sau khi bổ sung tracing

Cập nhật ngày 23/11/2026. Frontend Node 4.8 đã nạp tracer; collector phiên bản 0.3 và context phiên bản 0.4.1. Không gọi thêm Gemini trong đợt này.

Soak trước batch `20261123T015437Z` đạt 600 giây, 21 mẫu và 305 lượt checkout, không có request lỗi. Kiểm tra UTC đạt; khoảng cách mẫu lớn nhất 30,78 giây. Kết quả chỉ xác nhận ổn định ngắn hạn.

| Ca reference | Client latency trung bình: baseline → fault → recovery | Traffic | Inject-confirmed → collector nhận alert |
|---|---|---|---|
| S0078, orders → shipping, delay 450 ms và jitter 20 ms | 4,75 → 618,34 → 11,38 ms | 91 checkout, 0 request lỗi | 71,40 giây |
| S0071, front-end → carts, loss 25% | 18,81 → 364,58 → 16,64 ms | 89 checkout, 0 request lỗi; 79 packet drop | 65,96 giây |

Controller chọn đúng source/destination; netem có packet counter; client span có peer phù hợp. Latency tăng khi fault và giảm sau cleanup. Recovery mean của ca delay vẫn cao hơn baseline, nên chưa thể kết luận hai phân bố giống nhau. Packet loss không đồng nghĩa HTTP request lỗi vì có thể truyền lại.

Cả hai ca có đủ metric, log và trace, không chạm cap hoặc có query/export error. Các kiểm tra cấu trúc đều đạt; không có lifecycle drift ngoài target hoặc tăng node-local OOM. Cuối batch, danh sách health issues rỗng.

Đây là review kỹ thuật của trợ lý. Review độc lập và admission còn chờ. Registry hiện có **10 attempt, 9 capture, 0/200 ca chính thức**. Hai ca mới là lượt lặp trên pipeline mới, không phải hai cấu hình lỗi độc nhất mới.

Ca delay có 5.930 dòng log và 884 trace ID; số span khác số trace. Context mới giữ tám directed edge quan sát, gồm đúng edge fault. Evidence index tra về raw theo service, trace ID và span ID. Không dùng ground truth để chọn context; quality review, ground truth và qdisc nằm riêng.

## Bằng chứng

- Batch và trạng thái cuối: `results/calibration-batches/20261123T020440392094Z/`.
- Delay: `data/candidates/CANDIDATE-20261123T020440486374-S0078/`.
- Loss: `data/candidates/CANDIDATE-20261123T020815385720-S0071/`.

Mỗi ca có quality review, effect review, network observation review, detector evidence và provenance. Audit dataset local đạt; 57 kiểm thử Python đạt. AppTest chạy đủ sáu tab, không có exception.

## Bước tiếp theo

Hai packet B1–B3 tại `results/approval/gemini-network-v041-20261123/{delay,loss}` đã qua check-only rồi được người dùng duyệt và chạy đủ sáu generation, ba embedding mới và một cache hit. Không retry/reindex. Xem [kết quả Gemini](GEMINI-NETWORK-V041.md).

Các packet dùng toàn cửa sổ development, có dữ liệu recovery. Không dùng chúng để báo live LLM TTD hoặc coi là cùng context với report cũ. B3 với prompt 0.2/context 0.4.1 đúng Top-1 ở hai ca mới; chưa phải kiểm chứng tổng quát.

Bộ phiếu mới đã bao gồm 25 report và 137 đoạn văn bản. Chưa có nhãn claim hoặc điểm chấm của con người. Chưa có benchmark chính thức hoặc bằng chứng ROI.
