# E0: Bộ Stanford Chess.com Knowledge Tracing

Ngày kiểm tra: 15/11/2026. Ticket: #15.

**Kết luận: dùng được cho lớp đánh giá 1**, kèm ba lưu ý ở mục "Hệ quả cho E1". Không cần phương án dự phòng.

## Nguồn và điều khoản

- **Trang môn học:** [CS398, Knowledge Tracing](https://web.stanford.edu/class/cs398/handouts/knowledge-tracing.html).
- **Starter bundle:** [starter_bundle.zip](https://web.stanford.edu/class/cs398/handouts/knowledge-tracing/starter_bundle.zip), 32 MB, cập nhật ngày 10/09/2026.
- **Điều khoản: không có.** Cả trang lẫn README đều không ghi giấy phép hay điều kiện sử dụng. Dữ liệu là lịch sử giải bài tập của người chơi Chess.com, được phát cho một buổi thực hành của môn CS398.
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
- `pre_rating`: rating giải bài tập (tactics rating) của người chơi trên Chess.com, trước lần giải. Khác với rating ván;
- `puzzle_rating_original`: rating bài tập trên Chess.com, cùng thang với `pre_rating` (không phải thang Lichess);
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
- Lần giải trùng thời điểm được xếp theo hash(số dòng trong file, seed). Chỉ có 4 nhóm trùng, tổng 12 dòng; đều là dòng lặp cùng người chơi, cùng bài tập, cùng thời điểm, và đều nằm sâu trong phần train. Vì vậy đổi seed chỉ đổi thứ tự vài dòng trong train, phần test giữ nguyên.

```sh
npm run data                                           # ở thư mục gốc: tải bundle và tạo phép chia
cd backend
uv run python -m chesscoach.experiments.e0_baselines   # chạy lại phép chia và in các bảng baseline
```

Kết quả: train 872.867 lần giải, test 218.760 lần giải (tỉ lệ đúng 0,4981). Cả hai lệnh đều ghi ra `backend/data/stanford/split/{train,test}.parquet` và `manifest.json`, mặc định seed 398.

Đã kiểm tra:
- Chạy lại với cùng seed thì ra đúng phép chia đó, kể cả thứ tự `seq` (so bằng md5). Với seed khác thì phần test giống hệt, phần train chỉ khác thứ tự các dòng trùng thời điểm.
- Không người chơi nào có lần giải test nằm trước lần giải train.
- Người chơi nào cũng có ít nhất một lần giải trong test.

## Baseline

Accuracy tính theo ngưỡng p ≥ 0,5. Leaderboard nhận cả xác suất lẫn nhãn 0/1, nhưng không ghi ngưỡng; 0,5 là cách đọc tự nhiên nhất. Tất cả các bản hiệu chỉnh chỉ fit trên phần train của phép chia.

**Toàn bộ phần test** (218.760 lần giải, tỉ lệ đúng 0,4981):

| Baseline | Accuracy | AUC | Log-loss | p trung bình |
| --- | ---: | ---: | ---: | ---: |
| Luôn đoán tỉ lệ đúng của train | 0,4981 | 0,5000 | 0,6932 | 0,500 |
| Elo sách giáo khoa: `pre_rating` vs `puzzle_rating_original` | 0,5079 | 0,5835 | 1,0711 | 0,826 |
| Rating Chess.com hiệu chỉnh: σ(a + b·Δ/400), a = −0,382, b = 0,530 | 0,5577 | 0,5835 | 0,6834 | 0,511 |
| *Elo sách giáo khoa với `puzzle_rating_ours`* | *0,5175* | *0,6504* | *1,0099* | *0,820* |
| *Hiệu chỉnh với `puzzle_rating_ours`* (a = −0,664, b = 0,935) | *0,6051* | *0,6504* | *0,6630* | *0,520* |

**Phần test, chỉ các bài tập có trong `test.csv` gốc** (9.415 bài tập, 38.674 lần giải, tỉ lệ đúng 0,4692):

| Baseline | Accuracy | AUC | Log-loss | p trung bình |
| --- | ---: | ---: | ---: | ---: |
| Luôn đoán tỉ lệ đúng của train | 0,4692 | 0,5000 | 0,6932 | 0,500 |
| Elo sách giáo khoa: `pre_rating` vs `puzzle_rating_original` | **0,4774** | 0,5763 | 1,1411 | 0,831 |
| Rating Chess.com hiệu chỉnh | **0,5472** | 0,5763 | 0,6869 | 0,513 |
| *Elo sách giáo khoa với `puzzle_rating_ours`* | *0,4873* | *0,6515* | *1,0567* | *0,818* |
| *Hiệu chỉnh với `puzzle_rating_ours`* | *0,6003* | *0,6515* | *0,6657* | *0,517* |

**So với con số công bố trên tập test ẩn:**
- **Elo sách giáo khoa:** công bố 47%. Đo trên đúng các bài tập của tập test gốc, nhóm được **47,7%**, nên **lặp lại được kết quả công bố**. Trên toàn bộ phần test thì được 50,8%, vì tập test gốc được chọn quanh những bài tập mà một mô hình đã hiệu chỉnh tốt thấy dễ: trên các bài tập này người chơi giải đúng ít hơn (46,9%), trong khi công thức chưa hiệu chỉnh vẫn đoán p ≈ 0,83.
- **Rating Chess.com:** công bố 59% là của Glicko-2 nội bộ Chess.com, bundle không có dự đoán của hệ này. Baseline gần nhất nhóm làm được là vẫn dùng rating Chess.com nhưng hiệu chỉnh trên train, đạt **54,7%** trên các bài tập của test gốc và 55,8% trên toàn bộ phần test. Phần còn thiếu so với 59% có thể đến từ độ bất định RD của Glicko-2 và việc Chess.com cập nhật rating bài tập liên tục; cả hai đều không có trong dữ liệu. Bản hiệu chỉnh làm hai việc:
  - thêm hệ số chặn để khớp tỉ lệ đúng 50% của dữ liệu đã cân bằng;
  - giảm độ dốc từ ln 10 ≈ 2,30 (Elo sách giáo khoa) xuống 0,53, tức còn khoảng 23%, vì hiệu rating ồn.

**Các dòng in nghiêng bị rò rỉ dữ liệu test.** README ghi rằng `puzzle_rating_ours` được ước lượng từ kết quả của *mọi người trong bộ dữ liệu*, tức là gồm cả phần nhóm tách ra làm test. Vì vậy 60,5% và 60,0% là con số lạc quan, không dùng làm mốc.

`puzzle_rating_original` cũng chỉ là một ảnh chụp duy nhất cho mỗi bài tập, không rõ chụp lúc nào. Nó có thể đã gồm kết quả của những lần giải về sau. Mức rò rỉ này nhẹ hơn nhiều vì rating được tính trên toàn bộ người chơi Chess.com, không chỉ 1.068 người này, nhưng vẫn là một giới hạn nên ghi trong báo cáo.

**Mốc cho E1:**
- **55,8%** (rating Chess.com hiệu chỉnh) và **50,8%** (Elo sách giáo khoa) trên toàn bộ phần test;
- **54,7%** và **47,7%** trên các bài tập của test gốc.

Hai dòng Elo sách giáo khoa và hiệu chỉnh có cùng AUC, vì hiệu chỉnh chỉ là biến đổi đơn điệu của cùng một hiệu rating: nó không đổi thứ hạng, chỉ đổi xác suất và ngưỡng.

## Hệ quả cho E1 (#16)

1. **Hiệu chỉnh xác suất là bắt buộc.** Mô hình năng lực trong app dùng θ khởi đầu ở 1500 và công thức Elo không có hệ số chặn. Trên dữ liệu đã cân bằng, nó sẽ lệch y như Elo sách giáo khoa. Khi so ở lớp 1, nên báo cả bản thô lẫn bản hiệu chỉnh: hoặc fit hệ số chặn trên train, hoặc nói rõ là dữ liệu đã cân bằng.
2. **Cần bảng chuyển chủ đề Chess.com sang kỹ năng.** Bản đồ kỹ năng hiện chỉ có chủ đề Lichess, trong khi Chess.com có 56 chủ đề với tên khác (ví dụ `Fork / Double Attack`, `Decoy / Deflection`, `Mate in 3+`).
3. **Thang rating khác ADR 0003.** ADR 0003 đặt θ trên thang rating bài tập Lichess. Trên bộ Stanford, mô hình năng lực phải chạy trên thang Chess.com: thay rating bài tập Lichess bằng `puzzle_rating_original`, và khởi tạo từ `pre_rating`. Việc này không mâu thuẫn với ADR, vì lớp 1 kiểm tra *cấu trúc* của mô hình (Elo theo kỹ năng có dự đoán tốt hơn Elo chung không), không kiểm tra con số θ trong app. Nhưng báo cáo phải nói rõ là đã đổi thang.
4. **Đặc trưng chỉ được dùng những gì biết trước lần giải:** không dùng `solve_time`. Dùng `puzzle_rating_ours` cho IRT là bị rò rỉ dữ liệu test, như đã nói ở trên. Nếu muốn có rating bài tập được hiệu chỉnh, phải tự fit trên phần train.
