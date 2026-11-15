# Năng lực θ nằm trên thang rating bài tập Lichess

θ dùng cùng thang với rating bài tập Lichess, vì công thức p_ui so θ trực tiếp với b_i. Rating ván trên Lichess hoặc Chess.com thường lệch rating bài tập hàng trăm điểm, nên chỉ được quy đổi thô thành tiên nghiệm kèm độ bất định lớn; 12 bài kiểm tra đầu vào sẽ chỉnh lại. Nhóm tham chiếu (dải 200 điểm) cũng chia theo θ, nên người chơi Lichess và Chess.com dùng chung một bảng μ_k.

## Phụ lục (15/11/2026, E1b)

θ vẫn cùng thang với rating bài tập Lichess, nhưng thang s của công thức xác suất đổi từ 400/ln 10 thành gấp 3 lần: một chênh 400 rating không còn nghĩa là tỉ lệ 10:1 mà chỉ khoảng 2,2:1. Lý do: trên dữ liệu thật (bộ Stanford), chênh rating dự báo kết quả yếu hơn nhiều so với công thức Elo giả định. Bằng chứng này đến từ rating Chess.com; với rating Lichess thì bước hiệu chỉnh xác suất trong app (#22) sẽ học lại độ dốc từ dữ liệu. Xem docs/experiments/e1b-tuning.md.
