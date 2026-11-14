# Elo theo kỹ năng chạy trong app, BKT chỉ để so sánh

Mô hình năng lực chạy trong sản phẩm là Elo/IRT theo kỹ năng, chọn trước khi có kết quả lớp 1. Lý do: hàm chấm điểm cần xác suất giải đúng p_ui có tính đến rating bài tập, mà BKT không dùng độ khó của bài. BKT (pyBKT) chỉ chạy offline: làm đối chứng ở lớp 1 và làm người học mô phỏng ở lớp 3. Nhờ vậy người học mô phỏng không dùng cùng công thức với hệ gợi ý, tránh việc hệ thống tự chấm điểm cho chính mình.
