# Chess Coach

Hệ gợi ý bài tập cờ cho người chơi nghiệp dư, dựa trên mô hình năng lực của từng người; mục tiêu là người chơi tiến bộ, không phải người chơi thích.

## Ngôn ngữ

### Nội dung luyện tập

**Bài tập**:
Một thế cờ trong kho Lichess kèm lời giải, độ khó và các chủ đề; đây là item mà hệ thống gợi ý.
_Tránh_: puzzle, câu đố, bài

**Chủ đề**:
Nhãn mà Lichess gắn cho bài tập (73 loại, ví dụ `fork`, `backRankMate`, `rookEndgame`). Có hai loại: chủ đề kỹ năng và chủ đề mô tả.
_Tránh_: theme, tag

**Chủ đề mô tả**:
Chủ đề chỉ mô tả bài tập mà không nói kỹ năng nào: độ dài, mức lợi thế, giai đoạn ván, nguồn ván (ví dụ `short`, `crushing`, `endgame`, `master`). Không thuộc kỹ năng nào.
_Tránh_: meta theme

**Kỹ năng**:
Một trong 15–20 nhóm chủ đề mà mô hình năng lực theo dõi riêng; mỗi chủ đề kỹ năng thuộc đúng một kỹ năng. Bài tập không có chủ đề kỹ năng nào thuộc kỹ năng "bỏ lỡ chiến thuật".
_Tránh_: skill, năng lực con, mảng

**Nhóm kỹ năng**:
Một trong vài nhóm gom các kỹ năng gần nhau (ví dụ "Chiếu hết", "Tàn cuộc") để hiển thị tổng quan trên radar; mô hình năng lực không dùng nhóm.
_Tránh_: nhóm radar, nhóm (nói trống, dễ lẫn với Nhóm tham chiếu)

**Bản đồ kỹ năng**:
Bảng duy nhất gán mỗi chủ đề kỹ năng vào một kỹ năng, dùng chung cho cả bài tập lẫn lỗi trong ván. Có thêm một phần chuyển chủ đề Chess.com sang cùng các kỹ năng đó, chỉ dùng cho đánh giá trên bộ Stanford.

**Rating bài tập**:
Độ khó của một bài tập theo thang Glicko-2 của Lichess.
_Tránh_: Elo của bài, độ khó (khi cần con số)

**Độ lệch rating bài tập**:
Phần cộng thêm vào rating bài tập, học từ kết quả các lần giải, khi rating gốc không khớp độ khó thật. Hiện chỉ dùng trong đánh giá.
_Tránh_: độ khó học được, item difficulty

**Lần giải**:
Một lần người chơi làm một bài tập. Lần giải chỉ đúng khi mọi nước đều đúng ngay lần đầu; một nước được tính đúng nếu trùng lời giải hoặc chiếu hết.
_Tránh_: attempt, lượt làm

### Năng lực người chơi

**Người chơi**:
Một người dùng của hệ thống, đăng nhập bằng email, có một năng lực và một hồ sơ điểm yếu duy nhất.
_Tránh_: user, học viên, account

**Tài khoản liên kết**:
Tài khoản Lichess hoặc Chess.com mà người chơi gắn vào hồ sơ để hệ thống lấy ván; mỗi người chơi có 0–2 tài khoản liên kết, và lỗi từ mọi tài khoản dồn vào cùng điểm yếu.
_Tránh_: tài khoản (không rõ loại), username

**Nhóm tham chiếu**:
Những người chơi có năng lực chung trong cùng một dải 200 điểm; dùng để làm trơn điểm yếu và so sánh trong giải thích.
_Tránh_: người cùng Elo, peer group

**Năng lực**:
Ước lượng θ về sức giải bài tập của một người chơi, gồm năng lực chung và độ lệch theo từng kỹ năng, nằm cùng thang với rating bài tập. Năng lực ở một kỹ năng là năng lực chung cộng độ lệch của kỹ năng đó.
_Tránh_: Elo (khi nói về θ), điểm, level

**Hiệu chỉnh xác suất**:
Bước sửa xác suất giải đúng mà mô hình năng lực dự đoán, để nó khớp tỉ lệ giải đúng thật; học chung cho cả app từ lịch sử lần giải. Khác với việc bài kiểm tra đầu vào chỉnh lại năng lực ban đầu.
_Tránh_: calibration, hiệu chỉnh (nói trống)

**Hồ sơ kỹ năng**:
Màn hình và dữ liệu cho người chơi xem năng lực chung, năng lực từng kỹ năng kèm khoảng tin cậy, và radar theo nhóm kỹ năng.
_Tránh_: profile, trang cá nhân

**Rating ván**:
Rating của người chơi trên Lichess hoặc Chess.com khi chơi ván; chỉ dùng làm tiên nghiệm thô cho năng lực.
_Tránh_: Elo (không nói rõ nền tảng)

**Bài kiểm tra đầu vào**:
Bộ 12 bài tập người chơi mới làm để hiệu chỉnh năng lực ban đầu.
_Tránh_: placement test, bài test

### Gợi ý

**Buổi luyện**:
Danh sách top-K bài tập được gợi ý cho lần luyện tiếp theo, mỗi bài kèm lý do; đây là đầu ra chính của hệ thống.
_Tránh_: session, bài học

**Bài ôn lại**:
Một bài tập mới, chưa làm bao giờ, thuộc kỹ năng mà người chơi vừa giải sai gần đây. Hệ thống không bao giờ đưa lại đúng một bài đã làm.
_Tránh_: bài làm lại, flashcard

**Kỹ năng tiên quyết**:
Kỹ năng nên vững trước khi luyện một kỹ năng khác. Kỹ năng tiên quyết chưa vững chỉ làm giảm ưu tiên của kỹ năng sau, không khóa nó.
_Tránh_: điều kiện mở khóa

**Thời gian luyện mỗi ngày**:
Số phút người chơi khai sẽ luyện mỗi ngày; quyết định số bài tập của buổi luyện (30 phút khoảng 17 bài tập).
_Tránh_: quỹ thời gian, daily budget

**Lộ trình**:
Dự kiến các buổi luyện trong 14 ngày tới, tính lại sau mỗi buổi; chỉ để xem trước, không phải kế hoạch cố định.
_Tránh_: giáo trình, kế hoạch học

### Ván cờ và điểm yếu

**Lỗi**:
Một nước đi của người chơi trong ván thật (Lichess hoặc Chess.com) làm xác suất thắng tụt mạnh, từ mức mistake trở lên. Lỗi do bị đối thủ khai thác và lỗi bỏ lỡ cơ hội của mình được tính như nhau.
_Tránh_: sai lầm, blunder (khi nói chung)

**Motif**:
Chủ đề được nhận diện cho một lỗi bằng bộ gắn chủ đề; motif đi qua bản đồ kỹ năng như mọi chủ đề khác. Lỗi không nhận diện được motif thuộc kỹ năng "bỏ lỡ chiến thuật".
_Tránh_: pattern, mẫu

**Điểm yếu**:
Tỉ lệ lỗi mỗi ván của một người ở một kỹ năng, đã làm trơn về mức trung bình của người cùng Elo.
_Tránh_: lỗ hổng, weakness score
