# Phạm vi và nghiệm thu

| Mốc | Điều kiện nghiệm thu | Bằng chứng |
|---|---|---|
| M0 Môi trường | Docker engine hoạt động; công cụ có phiên bản; image/platform được xác minh | doctor, image audit |
| M1 Benchmark | Sock Shop hoạt động; traffic qua service mục tiêu; tài nguyên ổn định | manifest thực tế, smoke report, traffic summary |
| M2 Telemetry | Truy vấn được metric/log/trace; alert tới webhook | truy vấn, trace ID, webhook event |
| M3 Chaos và dữ liệu | Ba fault class tái lập; recovery; context tách khỏi ground truth | scenario, case JSON, evidence |
| M4 Trợ lý | Report đúng schema; evidence truy ngược; RAG chỉ dùng reference | report, retrieval records |
| M5 Đánh giá | Khoảng 200 case; split 120/40/40 theo scenario group; B0–B3 cùng test | split manifest, raw results, evaluation |
| M6 Bàn giao | Tái lập được; demo live/replay; phân tích sai số và chi phí | runbook, báo cáo, demo protocol |

Không index test case vào Qdrant. Không đưa chaos metadata hoặc nhãn đáp án vào context. Không kết luận tiết kiệm giờ công chỉ từ latency sinh report. Không yêu cầu accuracy đạt một con số chọn trước.
