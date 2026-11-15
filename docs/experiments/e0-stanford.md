# E0: Bộ Stanford Chess.com Knowledge Tracing

Ngày kiểm tra: 15/11/2026. Ticket: #15.

**Kết luận: dùng được cho lớp đánh giá 1**, kèm ba lưu ý ở mục "Hệ quả cho E1". Không cần phương án dự phòng.

## Nguồn và điều khoản

- **Trang môn học:** [CS398, Knowledge Tracing](https://web.stanford.edu/class/cs398/handouts/knowledge-tracing.html).
- **Starter bundle:** [starter_bundle.zip](https://web.stanford.edu/class/cs398/handouts/knowledge-tracing/starter_bundle.zip), 32 MB, cập nhật ngày 10/09/2026.
- **Điều khoản: không có.** Cả trang lẫn README đều không ghi giấy phép hay điều kiện sử dụng. Dữ liệu là lịch sử giải bài tập của người chơi Chess.com, được phát cho bài tập trên lớp.
- **Cách nhóm dùng:**
  - Chỉ dùng để đánh giá offline. Không phân phối lại: dữ liệu nằm trong `backend/data/stanford/` (đã có trong `.gitignore`), không commit.
  - Trích dẫn trang CS398 trong báo cáo.
  - Nên hỏi giảng viên một câu cho chắc khi gửi đề cương.

## Kích thước và cột

| File | Số dòng | Nội dung |
| --- | ---: | --- |
| `train.csv` | 1.091.627 lần giải | 1.068 người chơi, 76.965 bài tập, 05/06–19/11/2021 |
| `test.csv` | 20.649 lần giải | 921 người chơi, 9.415 bài tập, 08/07–03/12/2021; ẩn nhãn |
| `puzzles.csv` | 76.965 bài tập | 536 bài tập không có metadata |

Cột thật của `train.csv`:
- `user_id`, `tactics_problem_id`, `create_date`;
- `pre_rating`: rating người chơi trên Chess.com, trước lần giải;
- `puzzle_rating_original`: rating bài tập trên Chess.com;
- `puzzle_rating_ours`: rating bài tập do nhóm CS398 hiệu chỉnh lại;
- `puzzle_move_count`, `target_time`, `solve_time`, `is_correct`.

`test.csv` thêm cột `row_id` và không có `is_correct`.

Cột của `puzzles.csv`: `tactics_problem_id`, `fen`, `rating_is_provisional`, `times_played`, `themes`. Cột `themes` dùng 56 chủ đề của Chess.com, ngăn cách bằng dấu `;`.

Đặc điểm cần biết:
- **Dữ liệu đã được cân bằng: tỉ lệ đúng đúng 50,0%**, ổn định qua từng tháng. Tỉ lệ thật trên Chess.com cao hơn nhiều: Elo dự đoán trung bình p ≈ 0,80.
- Số lần giải mỗi người: ít nhất 5, trung vị 416, nhiều nhất 18.222.
- Tập `test.csv` gốc chia theo thời gian: mọi dòng đều nằm sau lần giải cuối của người đó trong train.
- `solve_time` chỉ biết được **sau** lần giải, nên không được dùng làm đặc trưng để dự đoán.

## Phép chia của nhóm

Tập test gốc ẩn nhãn, nên nhóm chia lại `train.csv`:
- Với mỗi người chơi, sắp lần giải theo `create_date` và lấy ceil(20%) lần giải cuối làm test.
- Lần giải trùng thời điểm (chỉ có 4 cặp) được xếp theo một hash cố định theo seed.

```sh
cd backend
uv run python -m chesscoach.experiments.e0_baselines --seed 398
```

Kết quả: train 872.867 lần giải, test 218.760 lần giải (tỉ lệ đúng 0,4981). Lệnh ghi ra `data/stanford/split/{train,test}.parquet` và `manifest.json`.

Đã kiểm tra:
- Chạy lại với cùng seed thì ra đúng phép chia đó (so bằng md5).
- Không người chơi nào có lần giải test nằm trước lần giải train.
- Người chơi nào cũng có ít nhất một lần giải trong test.

## Baseline

Đo trên phần test của phép chia, accuracy dùng ngưỡng 0,5 như leaderboard:

| Baseline | Accuracy | AUC | Log-loss | p trung bình |
| --- | ---: | ---: | ---: | ---: |
| Luôn đoán tỉ lệ đúng của train | 0,4981 | 0,5000 | 0,6932 | 0,500 |
| Elo sách giáo khoa: `pre_rating` vs `puzzle_rating_original` | **0,5079** | 0,5835 | 1,0711 | 0,826 |
| Rating Chess.com hiệu chỉnh trên train: σ(a + b·Δ/400), a = −0,382, b = 0,530 | **0,5577** | 0,5835 | 0,6834 | 0,511 |
| *Elo sách giáo khoa với `puzzle_rating_ours`* | *0,5175* | *0,6504* | *1,0099* | *0,820* |
| *Hiệu chỉnh với `puzzle_rating_ours`* | *0,6051* | *0,6504* | *0,6630* | *0,520* |

**So với con số công bố trên tập test ẩn:**
- **Elo sách giáo khoa:** 47% công bố, nhóm đo được 50,8%. Lệch là hợp lý: tập test ẩn được chọn quanh những lần giải mà một mô hình đã hiệu chỉnh tốt thấy dễ, nên đẩy công thức chưa hiệu chỉnh xuống dưới 50%. Phép chia của nhóm không chọn lọc như vậy. Trên cả hai tập, công thức này đều gần mức đoán bừa, vì nó dự đoán p ≈ 0,8 trên dữ liệu đã cân bằng về 50%.
- **Rating Chess.com:** 59% công bố là của Glicko-2 nội bộ Chess.com, bundle không có dự đoán của hệ này. Baseline gần nhất nhóm làm được là vẫn dùng rating Chess.com nhưng hiệu chỉnh lại trên train, đạt 55,8%. Cách hiệu chỉnh: thêm hệ số chặn để khớp tỉ lệ đúng 50%, và kéo độ dốc về 0,53 vì rating ồn.

**Các dòng in nghiêng bị rò rỉ dữ liệu test.** README ghi rằng `puzzle_rating_ours` được ước lượng từ kết quả của *mọi người trong bộ dữ liệu*, tức là gồm cả phần nhóm tách ra làm test. Vì vậy 60,5% là con số lạc quan, không dùng làm mốc. Mốc cho E1 là **55,8%** (rating Chess.com hiệu chỉnh) và **50,8%** (Elo sách giáo khoa).

Hai dòng Elo sách giáo khoa và hiệu chỉnh có cùng AUC, vì hiệu chỉnh chỉ là biến đổi đơn điệu của cùng một hiệu rating: nó không đổi thứ hạng, chỉ đổi xác suất và ngưỡng.

## Hệ quả cho E1 (#16)

1. **Hiệu chỉnh xác suất là bắt buộc.** Mô hình năng lực trong app dùng θ khởi đầu ở 1500 và công thức Elo không có hệ số chặn. Trên dữ liệu đã cân bằng, nó sẽ lệch y như Elo sách giáo khoa. Khi so ở lớp 1, nên báo cả bản thô lẫn bản hiệu chỉnh: hoặc fit hệ số chặn trên train, hoặc nói rõ là dữ liệu đã cân bằng.
2. **Cần bảng chuyển chủ đề Chess.com sang kỹ năng.** Bản đồ kỹ năng hiện chỉ có chủ đề Lichess, trong khi Chess.com có 56 chủ đề với tên khác (ví dụ `Fork / Double Attack`, `Decoy / Deflection`, `Mate in 3+`).
3. **Đặc trưng chỉ được dùng những gì biết trước lần giải:** không dùng `solve_time`. Dùng `puzzle_rating_ours` cho IRT là bị rò rỉ dữ liệu test, như đã nói ở trên. Nếu muốn có rating bài tập được hiệu chỉnh, phải tự fit trên phần train.
