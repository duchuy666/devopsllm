# Kế hoạch bàn giao trong 48 giờ

Lập ngày 23/11/2026 theo thông báo còn hai ngày để nộp. Dự kiến hạn ngày 25/11; người dùng xác nhận bản cuối bắt buộc 200 ca, có một reviewer độc lập và đồng ý đo trước khi xem đáp án test; giờ nộp cụ thể chưa được xác nhận. Đây là kế hoạch ưu tiên, không phải cam kết đã hoàn thành hoặc đã được giảng viên chấp thuận giảm phạm vi.

## Yêu cầu đang giữ nguyên

Khoảng 200 case, ba nhóm 67/67/66, grouped split 120/40/40, B0–B3 cùng case/cutoff, review và bằng chứng tái lập. Không tự giảm quy mô, đổi nhãn pilot thành test hoặc tăng admission bằng cách sửa trạng thái.

Trước đợt prospective có 10 attempt/9 capture development, 25 report Gemini; B3 đúng Top-1 ở hai ca mạng mới, chưa phải test accuracy. Official admission 0/200, release prospective v2 đã ghim 44 file và cửa sổ ±30 giây offline; benchmark cuối và review độc lập còn chờ. Có 89 kiểm thử Python đạt và bản demo local hoạt động.

## Ước lượng tải theo runner

Mỗi lượt traffic được cấp 120 giây cộng fault duration; riêng Pod failure dùng 30 giây quan sát fault. Tổng traffic budget của 200 dòng plan hiện tại là 9,5 giờ. Có 66 ca Pod failure; receipt bị mất hiệu lực khi Pod UID thay đổi nên cần soak mới trước ca sau, tối thiểu khoảng 11 giờ soak cho chuỗi này. Hai khoản cộng khoảng 20,5 giờ theo cấu hình hiện tại, chưa gồm export, lỗi, chạy lại, thời gian người review và viết báo cáo.

Đây là số danh nghĩa để lập lịch; không chứng minh có thể thu và admission đủ 200 case trong thời gian đó. Không bỏ health gate, UTC gate, cleanup hoặc group split để rút ngắn lịch. Không mặc định các capture cũ có thể admission dưới protocol mới.

## Thứ tự ưu tiên

| Khoảng giờ từ lúc chốt phạm vi | Việc cần hoàn thành | Đầu ra kiểm chứng được |
|---|---|---|
| 0–4 | Xác nhận loại bản nộp; chốt cutoff/protocol, thu hồi các claim chưa có bằng chứng; kiểm baseline và tuyến demo | Checklist phạm vi, cấu hình có phiên bản, báo cáo readiness |
| 4–24 | Nếu protocol và testbed đạt: thu tuần tự theo plan; giao reviewer kiểm dữ liệu/runbook ngay khi có | Raw/query/timestamps/provenance, quality review, số admitted thật |
| 24–34 | Review và chốt reference/validation; chỉ mở test sau freeze và có phạm vi API được duyệt | Freeze có hash, kết quả cùng cutoff, mọi lỗi giữ trong thống kê |
| 34–44 | Hoàn thiện báo cáo, bảng kết quả/sai số/giới hạn, hướng dẫn cài/chạy và demo replay | Hồ sơ nộp phản ánh đúng số liệu đã có |
| 44–48 | Dừng thêm tính năng, kiểm gói bàn giao trên môi trường sạch khi có thể, diễn tập và dự phòng | Source/config không chứa key, checklist tái lập, bản demo có phương án offline |

Các khoảng có thể chồng lấp với người review, nhưng trên cluster vẫn chỉ một fault tại một thời điểm. Không tự chạy nền sau khi cuộc trao đổi kết thúc hoặc coi lịch dự kiến là kết quả đã có.

## Phương án theo loại bản nộp

- Nếu bắt buộc đủ 200 case và benchmark cuối: phải giữ nguyên yêu cầu. Cần chốt ngay protocol, người review, thời gian máy chạy liên tục và phạm vi API. Nếu không đáp ứng, công bố thiếu hụt và trao đổi với giảng viên; không gọi bản nộp là đã hoàn thành toàn bộ thực nghiệm.
- Nếu là prototype/tiến độ: ưu tiên source chạy được, demo live/replay, bằng chứng của năm biến thể, so sánh development và danh sách hạn chế. Số case thực tế phải ghi đúng; mục tiêu 200 vẫn là phần chưa hoàn thành.
- Nếu giảng viên cho phép giảm quy mô: ghi rõ phạm vi được chấp thuận, protocol và split mới trước khi thu/chấm. Không âm thầm sửa kế hoạch 200 hiện có.

## Các đầu vào bên ngoài còn cần

Giờ nộp cụ thể; reviewer thực hiện phiên đo và phiếu review theo RB16; máy được giữ thức/cắm nguồn; phạm vi API mới nếu thực hiện thêm benchmark. Sáu generation của hai gói mạng vừa được duyệt đã dùng hết, không tự gọi thêm.

## Hồ sơ đã có để đưa vào bản nộp

Sản phẩm/UI, pipeline telemetry/alert/context/RAG/Gemini, B0, runner và quality audit, 16 runbook vận hành/5 runbook tri thức, backup/restore proofs, short-soak proofs, report và usage ledger. Phiếu review hiện chỉ là mẫu chờ người điền; không dùng chúng như kết quả review đã thực hiện.

## Trạng thái collection mới

Journal đang hoạt động: `results/dataset-collection/20261123T122308Z/journal.json`, release `20261123-prospective-v2`. Bảy ca reference đã thu được chuyển tiếp nguyên setting trước heldout; plan 0.3 phân biệt 200 cấu hình danh nghĩa, giữ split và nhóm. Không tính capture thành admission. Reviewer có thể review reference/validation trong lúc thu; chỉ mở đáp án test sau đủ 14 nhiệm vụ đo. Không gọi Gemini mới trước khi packet và phạm vi được duyệt.
