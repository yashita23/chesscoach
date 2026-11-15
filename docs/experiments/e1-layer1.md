# E1: Lớp đánh giá 1, dự đoán đúng/sai trên dữ liệu thật

Ngày chạy: 15/11/2026. Ticket: #16. Dữ liệu và phép chia: [E0](e0-stanford.md).

**Kết luận:** Elo theo kỹ năng (mô hình chạy trong app) dự đoán tốt hơn Elo chung trên mọi chỉ số, và vẫn được hiệu chỉnh tốt. IRT có accuracy và AUC cao nhất nhưng tự tin quá mức. BKT hiệu chỉnh rất tốt nhưng phân biệt kém hơn Elo theo kỹ năng, nên kết quả **ủng hộ ADR 0002**: giữ Elo theo kỹ năng trong app, BKT chỉ để so sánh và làm người học mô phỏng.

## Cách chạy lại

```sh
npm run data                       # ở thư mục gốc, nếu chưa có dữ liệu
cd backend
for m in elo skill_elo irt bkt; do for s in 0 1 2; do
  uv run python -m chesscoach.experiments.e1_layer1 predict --model $m --seed $s
done; done
uv run python -m chesscoach.experiments.e1_layer1 report
```

Elo chung, Elo theo kỹ năng và IRT mỗi lần chạy mất dưới 40 giây. BKT (pyBKT) mất 72–80 phút mỗi seed, vì trên Windows pyBKT chạy bằng Python thuần; ba seed chạy song song được bằng ba tiến trình. pyBKT 1.4 cần `numpy<2` và `scikit-learn<1.6` (đã ghim trong `backend/pyproject.toml`).

## Bốn mô hình

Mọi mô hình dùng phép chia theo thời gian của E0: 872.867 lần giải train, 218.760 lần giải test. Thang rating là của Chess.com (`puzzle_rating_original`). Không dùng `puzzle_rating_ours` vì nó bị rò rỉ dữ liệu test (xem E0).

| Mô hình | Cách dự đoán |
| --- | --- |
| Elo chung | Module mô hình năng lực của app (`chesscoach.ability`), coi bài tập không có kỹ năng nào. Năng lực khởi tạo từ `pre_rating` của lần giải đầu; dự đoán trực tuyến: đoán từng lần giải trước khi biết kết quả, rồi cập nhật |
| Elo theo kỹ năng | Cùng module, cùng cách chạy; kỹ năng lấy từ chủ đề Chess.com qua bản đồ kỹ năng của app |
| IRT 1PL | p = σ(θ người chơi − b bài tập + c), fit bằng Adam trên phần train; θ và b co về mức lấy từ rating Chess.com. θ giữ cố định khi dự đoán phần test |
| BKT | pyBKT, mỗi kỹ năng một mô hình (biết/chưa biết, học, đoán mò, trượt tay), fit trên phần train; dự đoán trực tuyến qua lịch sử. Lần giải nhiều kỹ năng: lấy trung bình dự đoán của các kỹ năng |

Chủ đề Chess.com được quy về kỹ năng bằng bảng `CHESSCOM_THEMES` trong `chesscoach.skills`, phần mở rộng của bản đồ kỹ năng:
- 44 chủ đề kỹ năng và 12 chủ đề mô tả;
- `Passed Pawns` được coi là chủ đề mô tả, vì nó gắn cho gần nửa số bài tập;
- vì Chess.com gắn ít nhãn chiến thuật, 51% bài tập chỉ có chủ đề mô tả và rơi vào kỹ năng "bỏ lỡ chiến thuật".

## Kết quả

Trên phần test, mean ± std qua 3 seed (0, 1, 2):

| Mô hình | Accuracy | AUC | Log-loss | p trung bình |
| --- | ---: | ---: | ---: | ---: |
| *Mốc E0: rating Chess.com hiệu chỉnh* | *0,5577* | *0,5835* | *0,6834* | *0,511* |
| Elo chung (thô) | 0,5704 ± 0,0000 | 0,5999 ± 0,0000 | 0,7170 ± 0,0000 | 0,490 |
| Elo chung (hiệu chỉnh Platt) | 0,5698 ± 0,0000 | 0,5999 ± 0,0000 | 0,6760 ± 0,0000 | 0,502 |
| Elo theo kỹ năng (thô) | 0,5885 ± 0,0000 | 0,6245 ± 0,0000 | 0,7030 ± 0,0000 | 0,492 |
| **Elo theo kỹ năng (hiệu chỉnh Platt)** | **0,5888 ± 0,0000** | **0,6245 ± 0,0000** | **0,6678 ± 0,0000** | 0,501 |
| IRT | 0,6000 ± 0,0000 | 0,6489 ± 0,0000 | 0,6978 ± 0,0000 | 0,415 |
| BKT (pyBKT) | 0,5696 ± 0,0018 | 0,6030 ± 0,0010 | 0,6767 ± 0,0000 | 0,498 |

Hiệu chỉnh Platt: σ(a + b·logit p), với a, b fit trên dự đoán của phần train.

**Độ lệch chuẩn bằng 0 ở hai mô hình Elo là thật, không phải lỗi:** hai mô hình này tất định, và phép chia không đổi theo seed (xem E0). Ở IRT, seed chỉ làm nhiễu rất nhỏ điểm khởi tạo, rồi tối ưu hội tụ về cùng một nghiệm. Seed chỉ thực sự có tác dụng ở BKT, qua điểm khởi tạo của EM.

**So với mốc E0** (rating Chess.com hiệu chỉnh: 55,8% accuracy, AUC 0,584, log-loss 0,683):
- Elo chung: tốt hơn trên cả ba chỉ số (57,0%, 0,600, 0,676), nhờ cập nhật năng lực sau mỗi lần giải.
- Elo theo kỹ năng: tốt hơn Elo chung **+1,9 điểm accuracy, +0,025 AUC, −0,008 log-loss**. Đây là bằng chứng chính cho việc theo dõi năng lực theo từng kỹ năng.
- Elo theo kỹ năng cũng tốt hơn BKT: **+1,9 điểm accuracy, +0,022 AUC, −0,009 log-loss**.
- IRT có accuracy và AUC cao nhất (60,0%, 0,649), nhưng log-loss kém nhất (0,698) vì tự tin quá mức. Nếu sau này muốn dùng IRT, phải hiệu chỉnh lại xác suất của nó.

### Độ hiệu chỉnh

![Độ hiệu chỉnh trên phần test](e1-calibration.png)

Bảng số của biểu đồ (seed 0; chỉ vẽ các khoảng có từ 500 lần giải; dạng: p dự đoán → tỉ lệ đúng thật):

| Mô hình | Các khoảng p (số lần giải) |
| --- | --- |
| Elo chung | 0,28 → 0,27 (1.705); 0,37 → 0,35 (21.482); 0,46 → 0,45 (84.623); 0,55 → 0,54 (88.238); 0,63 → 0,63 (19.588); 0,74 → 0,81 (1.800); 0,85 → 0,92 (1.023) |
| Elo theo kỹ năng | 0,27 → 0,26 (4.636); 0,36 → 0,34 (28.722); 0,45 → 0,45 (74.621); 0,55 → 0,55 (77.503); 0,63 → 0,64 (28.987); 0,74 → 0,78 (2.458); 0,85 → 0,91 (1.225) |
| IRT | 0,07 → 0,26 (10.152); 0,15 → 0,33 (29.173); 0,25 → 0,40 (35.536); 0,35 → 0,47 (36.116); 0,45 → 0,52 (33.370); 0,55 → 0,58 (28.172); 0,65 → 0,63 (21.699); 0,75 → 0,69 (14.693); 0,84 → 0,76 (7.163); 0,95 → 0,86 (2.686) |
| BKT | 0,38 → 0,37 (52.413); 0,45 → 0,47 (24.645); 0,53 → 0,53 (102.576); 0,61 → 0,61 (37.433); 0,75 → 0,75 (1.175) |

- **Hai mô hình Elo bám sát đường chéo** ở vùng có nhiều dữ liệu (p 0,3–0,65, chiếm khoảng 95% lần giải); ở đuôi trên thì hơi khiêm tốn. Hàm chấm điểm của buổi luyện dùng p quanh 0,7, nằm đúng vùng này.
- Tuy dữ liệu đã cân bằng về 50% đúng, hai mô hình Elo **không cần hiệu chỉnh thêm**: năng lực θ tự giảm về đúng mức sau vài lần giải. Hiệu chỉnh Platt chỉ cải thiện log-loss một chút (0,717 → 0,676 với Elo chung), và gần như không đổi accuracy.
- **IRT tự tin quá mức:** khi nó đoán p ≈ 0,07 thì tỉ lệ đúng thật là 0,26. Lý do là 76.965 bài tập mà phần lớn chỉ có vài lần giải, nên b bị fit quá sát; thêm nữa θ không cập nhật trong phần test. Accuracy cao nhất nhưng xác suất không dùng thẳng được cho hàm chấm điểm.
- **BKT hiệu chỉnh gần như hoàn hảo nhưng dè dặt:** mọi dự đoán nằm trong khoảng 0,38–0,75. BKT không biết độ khó của bài tập (một bài fork rating 800 và một bài rating 2.000 được đoán như nhau), nên không tách được lần giải dễ khỏi lần giải khó. Kết quả là AUC 0,603, gần Elo chung và kém Elo theo kỹ năng 0,022. Đây là đúng lý do ADR 0002 chọn Elo theo kỹ năng để chạy trong app.

## Phân bố năng lực cho lớp 3

`e1-skill-distribution.json` ghi phân bố năng lực sau lần giải cuối của từng người chơi, theo mô hình Elo theo kỹ năng:
- θ: trung bình 1.488, độ lệch chuẩn 365 (thang Chess.com, 1.068 người chơi);
- θₖ (đã co) của từng kỹ năng: chỉ tính người chơi có ít nhất 10 lần giải ở kỹ năng đó, độ lệch chuẩn khoảng 40–80 rating.

Người học mô phỏng ở lớp 3 (#19) lấy mẫu năng lực ẩn từ phân bố này. Nên dùng độ lệch chuẩn của θₖ chứ không dùng trung bình, vì trung bình phụ thuộc vào việc Chess.com chọn bài tập nào cho kỹ năng nào.

## Giới hạn

- Thang rating là của Chess.com, không phải thang rating bài tập Lichess như ADR 0003. Kết quả này đánh giá *cấu trúc* của mô hình, không đánh giá con số θ trong app.
- Các hằng số K, σ và độ co của mô hình năng lực vẫn là giá trị ban đầu, chưa tinh chỉnh. Nếu tinh chỉnh thì phải dùng một phần tách ra từ train, không dùng phần test.
- `puzzle_rating_original` là một ảnh chụp duy nhất cho mỗi bài tập, có thể đã gồm kết quả của những lần giải về sau (xem E0).
- DKT chưa làm; nó nằm trong tuần đệm.
