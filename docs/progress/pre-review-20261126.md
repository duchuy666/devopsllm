# Kiểm tra cấu trúc tự động trước review — 26/11/2026 19:20

Chạy `experiments.review_case.review` cho 57 ca đã thu (journal 20261126T033214Z). Đây là kiểm tra máy, KHÔNG phải review độc lập.

- 56 ca: đạt mọi kiểm tra cấu trúc. Reviewer chỉ cần mở tab Review dữ liệu, đối chiếu bằng chứng và lưu quyết định.
- 1 ca cần từ chối: **S0110** (validation) — `non_target_lifecycle_unchanged` lỗi: user-db OOMKilled và front-end Error lúc 08:40:51Z, ngoài mục tiêu tiêm lỗi.

Ưu tiên duyệt 11 ca test trước để mở khóa benchmark chính thức (cần ≥10 ca test admitted, đủ 3 nhóm lỗi).
