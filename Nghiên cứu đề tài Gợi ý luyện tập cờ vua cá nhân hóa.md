# Nghiên cứu đề tài: Gợi ý luyện tập cờ vua cá nhân hóa

Nov 13, 2026 · @Licht Nguyen

## 1. Tóm tắt kết luận

Đề tài khả thi trong 3–4 tuần và đủ phức tạp để lấy điểm cao, nhưng phải đóng khung lại: lõi là **gợi ý bài tập cờ (puzzle) dựa trên mô hình năng lực của người chơi**, còn lộ trình 14 ngày chỉ là cách trình bày kết quả gợi ý.

- **Dữ liệu đủ và mới.** Kho bài tập Lichess có 6.057.356 bài (giấy phép CC0, cập nhật 29/07/2026), mỗi bài có độ khó, chủ đề chiến thuật và độ phổ biến.
- **Có dữ liệu thật để đánh giá offline.** Bộ Chess.com Knowledge Tracing của môn Stanford CS398 ghi lịch sử giải bài đúng/sai theo thời gian. Baseline rating của Chess.com đạt khoảng 59% accuracy, Elo sách giáo khoa khoảng 47%: mục tiêu rõ để vượt.
- **Bản thiết kế của ChatGPT có ý demo tốt nhất:** hai người cùng Elo 1200 nhận hai lộ trình khác nhau. Nhưng nó thiếu phần đánh giá, stack quá nặng cho 3 người, và dễ bị xem là trùng nhóm "lộ trình học tập cá nhân hóa".
- **Cách tránh trùng:** nói rõ item là bài tập cờ trong kho 6 triệu bài, bài toán là xếp hạng item theo xác suất giải đúng và điểm yếu của từng người. Chương nào của môn học cũng có chỗ dùng (mục 2).

## 2. Bài toán và cách đóng khung thành hệ gợi ý

Hệ thống gợi ý cho mỗi người chơi nghiệp dư (Elo khoảng 800–1800) danh sách bài tập cho buổi luyện tiếp theo, sao cho họ học được nhiều nhất. Khác gợi ý phim hay nhạc: mục tiêu không phải "người dùng thích" mà "người dùng tiến bộ".

Bốn yêu cầu với một bài được gợi ý:

1. **Vừa sức:** xác suất giải đúng dự đoán khoảng 60–80% (vùng phát triển gần). Dễ quá thì không học được gì, khó quá thì nản.
2. **Nhắm đúng điểm yếu:** ưu tiên kỹ năng người chơi hay sai trong ván thật và trong bài tập.
3. **Đa dạng, không lặp:** không dồn 10 bài cùng một mẫu, không gợi ý lại bài đã làm.
4. **Thích nghi:** mỗi lần giải xong, hồ sơ năng lực cập nhật và danh sách tiếp theo thay đổi.

| Thành phần | Trong đề tài này |
| --- | --- |
| Người dùng | Người chơi, có Elo và có thể có tài khoản Lichess |
| Item | Bài tập trong kho Lichess: thế cờ (FEN), lời giải, độ khó, chủ đề |
| Tương tác | Mỗi lần giải bài: đúng/sai, số lần thử, thời gian; các ván cờ đã chơi (PGN) |
| Đầu vào | Rating ván (tiên nghiệm thô), thời gian học mỗi ngày, 12 bài kiểm tra đầu vào, tùy chọn liên kết 0–2 tài khoản Lichess/Chess.com |
| Đầu ra | Buổi luyện: top-K bài kèm lý do (màn hình chính); hồ sơ kỹ năng; lộ trình 14 ngày chỉ là tab xem trước |

Đề tài chạm vào gần như mọi chương của môn, đây là điểm cộng về độ phức tạp bài toán:

| Chương môn học | Dùng ở đâu |
| --- | --- |
| Lọc cộng tác | IRT/Elo là phân rã ma trận người–bài một chiều; mở rộng thành nhiều chiều theo chủ đề |
| Dựa trên nội dung | Chọn bài theo chủ đề, độ khó, giai đoạn ván cờ của bài |
| Dựa trên tri thức | Luật về kỹ năng tiên quyết (chiếu hết 1 nước trước 2 nước), ràng buộc thời gian học |
| Theo phiên / chuỗi | Chuỗi lần giải bài để dự đoán đúng/sai lần tới (BKT, DKT) |
| Lai ghép | Hàm chấm điểm gộp độ vừa sức, điểm yếu, độ đa dạng |
| Đánh giá | Ba lớp: dự đoán trên dữ liệu thật, kiểm chứng điểm yếu, mô phỏng người học (mục 7) |

## 3. Dữ liệu và công cụ có sẵn

Mọi thành phần khó đều đã có thư viện hoặc dữ liệu mở; nhóm chỉ cần ghép và viết phần mô hình năng lực, gợi ý và đánh giá.

### Dữ liệu

| Nguồn | Nội dung | Dùng cho | Ghi chú |
| --- | --- | --- | --- |
| [Kho bài tập Lichess](https://database.lichess.org/) | 6.057.356 bài; cột PuzzleId, FEN, Moves, Rating, RatingDeviation, Popularity, NbPlays, Themes, GameUrl, OpeningTags | Kho item để gợi ý; độ khó của item; nhãn chủ đề để đánh giá bộ nhận diện motif | CC0. Rating tính bằng Glicko-2, coi mỗi lần giải là một ván giữa người và bài. File nén .zst |
| [Stanford CS398 – Chess.com Knowledge Tracing](https://web.stanford.edu/class/cs398/handouts/knowledge-tracing.html) | train/test: user\_id, tactics\_problem\_id, create\_date, pre\_rating, puzzle\_rating\_original, puzzle\_rating\_ours, puzzle\_move\_count, target\_time, solve\_time, is\_correct; puzzles.csv: fen, times\_played, themes | Đánh giá offline mô hình năng lực: dự đoán đúng/sai lần giải tiếp theo | Test ẩn nhãn (leaderboard) nên chia lại train.csv. **Chưa kiểm tra kích thước và giấy phép** vì môi trường của mình không tải được file; nhóm tải [starter\_bundle.zip](https://web.stanford.edu/class/cs398/handouts/knowledge-tracing/starter_bundle.zip) ngay tuần 1 |
| [Lichess API – xuất ván của người chơi](https://lichess.org/api#tag/Games/operation/apiGamesUser) | `GET /api/games/user/{username}`, tham số `max`, `since`, `perfType`, `evals`, `analysed`; trả PGN hoặc ndjson | Lấy ván thật của người dùng; dựng persona demo; kiểm chứng điểm yếu | Có giới hạn tốc độ: tải trước và lưu lại, không gọi trực tiếp lúc demo |
| Chess.com Published-Data API | Kho ván theo tháng của người chơi (PGN) | Tài khoản liên kết Chess.com | Không có sẵn đánh giá máy nên luôn phải chạy Stockfish; User-Agent dùng tên client chung. Là phần cắt đầu tiên nếu trễ |

### Công cụ

| Công cụ | Vai trò | Ghi chú |
| --- | --- | --- |
| Stockfish + python-chess | Phân tích ván: đánh giá từng nước, tìm nước sai (điểm tụt mạnh), giai đoạn ván | Chạy CPU được; giới hạn độ sâu để kịp thời gian |
| [lichess-puzzler, tagger/cook.py](https://github.com/ornicar/lichess-puzzler/blob/d02e3600671c2b4499b5bd179658813a4ade1452/tagger/cook.py) | Bộ gắn chủ đề mà Lichess dùng thật: `fork()`, `skewer()`, `hanging_piece`, `trapped_piece`, `discovered_attack`, `mate_in`… | Lấp đúng lỗ hổng ChatGPT nêu: phân loại sai lầm thành motif. Kiểm tra giấy phép trước khi chép code |
| [chess\_detect](https://github.com/aslyamov/chess_detect) ([PyPI](https://pypi.org/project/chess-detect/)) | Nhận diện fork, pin, skewer, chiếu phát hiện, ăn quân treo, tiêu diệt quân bảo vệ, quân bị nhốt từ PGN | MIT; phương án dự phòng hoặc so sánh với cook.py |
| [pyBKT](https://github.com/CAHLR/pyBKT) | Bayesian Knowledge Tracing: fit, predict, cross-validate | `pip install pyBKT` |
| [ChessPuzzleKit](https://pypi.org/project/ChessPuzzleKit/) | Đọc và lọc kho bài Lichess bằng Python | Tiện nhưng không bắt buộc; pandas đọc CSV cũng được |
| [Maia-2](https://github.com/CSSLab/maia2) | Dự đoán nước đi giống người theo từng mức Elo | Chỉ là mở rộng: dùng để làm người học mô phỏng thực tế hơn |
| React (Vite) + FastAPI + SQLite | Giao diện, API, đăng ký/đăng nhập email + mật khẩu, job nền phân tích ván | Chạy local, demo offline ([ADR 0001](docs/adr/0001-react-fastapi-thay-streamlit.md)); Streamlit + `chess.svg` là đường lùi |

## 4. Nghiên cứu và sản phẩm liên quan

Hướng này đang được nghiên cứu năm 2026, nên báo cáo có cơ sở để trích dẫn và so sánh, không phải ý tưởng tự nghiển.

### Nghiên cứu

| Công trình | Ý chính | Liên quan thế nào |
| --- | --- | --- |
| [Discovering High Quality Chess Puzzles with Offline Reinforcement Learning](https://rlj.cs.umass.edu/2026/papers/Paper147.html) (Nie, Badrinath, …, Brunskill, Piech; RLC 2026) | Học giá trị sư phạm của từng bài từ khoảng 1,5 tỷ lần giải trên Chess.com; tác động rõ nhất với người mới (Elo 100–1000), nhất là người đang chững lại | Chứng minh bài toán "chọn bài nào để học" có thật và đo được. Dữ liệu có vẻ không công khai, nên nhóm dùng bộ Stanford |
| [ExRec](https://arxiv.org/abs/2507.11060) | Gợi ý bài tập bằng knowledge tracing kết hợp RL | Khung lý thuyết cho phần "mô hình năng lực → chọn bài"; RL để ở hướng phát triển |
| [Maia-2](https://arxiv.org/abs/2409.20553) (NeurIPS 2024) | Dự đoán nước đi của người theo từng mức kỹ năng bằng attention theo Elo | Nguồn cho "người cùng Elo vẫn chơi khác nhau"; có thể dùng làm người học mô phỏng |
| [pyBKT](https://github.com/CAHLR/pyBKT) (EDM 2021) | Thư viện BKT chuẩn | Mô hình năng lực để so với Elo/IRT theo chủ đề |
| Deep Knowledge Tracing (Piech và cộng sự, NeurIPS 2015) | RNN trên chuỗi lần làm bài | Baseline nâng cao; bộ Stanford đã gợi ý DKT làm baseline |

Một số bài dự đoán độ khó bài cờ (GlickFormer, mô hình stacking trên khoảng 4,5 triệu bài) cũng có, nhưng không cần vì Lichess đã cho sẵn rating của từng bài.

### Sản phẩm

| Sản phẩm | Làm được gì | Khoảng trống đề tài lấp vào |
| --- | --- | --- |
| Lichess (Puzzles, Puzzle Dashboard) | Giải bài theo rating hoặc theo chủ đề tự chọn; thống kê chủ đề mạnh/yếu | Người dùng tự chọn chủ đề; không nối với lỗi trong ván thật |
| Chess.com (Puzzles, Game Review, Insights) | Phân tích ván, phân loại nước đi, bài tập | Đóng, không giải thích vì sao gợi ý bài này |
| Chessigma, Chessalyz | Phân tích ván và hồ sơ kỹ năng | Không đánh giá công khai độ chính xác của hồ sơ |
| ChessDojo | Chương trình học theo mốc rating | Giáo trình chung theo Elo, ít cá nhân hóa theo lỗi |
| Maia Chess | Bot chơi giống người theo Elo | Không gợi ý bài tập |

Nét riêng của nhóm: khép kín vòng "lỗi trong ván thật → hồ sơ năng lực → bài vừa sức → cập nhật", có giải thích, và có số đo cho từng khâu.

## 5. Đánh giá bản thiết kế của ChatGPT

Khung 5 màn hình và kịch bản hai người cùng Elo 1200 nên giữ; phần cần sửa là cách đóng khung, cách đo và độ nặng của stack.

| Điểm trong bản thiết kế | Quyết định | Lý do và cách sửa |
| --- | --- | --- |
| Hai người cùng Elo 1200, hai lộ trình khác nhau | **Giữ** | Đây là minh chứng cá nhân hóa dễ hiểu nhất cho giảng viên. Dùng hai tài khoản Lichess thật cùng mức rating, hồ sơ lỗi khác nhau (ẩn tên khi trình chiếu) |
| Phân tích PGN bằng Stockfish | **Giữ, thu gọn** | Chạy trước và lưu kết quả; lúc demo chỉ phân tích trực tiếp 1 ván ngắn |
| Phân loại lỗi thành fork, pin… (ChatGPT để ở "nâng cao") | **Đưa vào MVP** | Không có bước này thì không nối được ván cờ với chủ đề bài tập. Đã có cook.py và chess\_detect nên không còn là việc khó |
| Radar 5 kỹ năng (chiến thuật, khai cuộc, trung cuộc, tàn cuộc, phòng thủ) | **Sửa** | 5 nhóm quá thô để chọn bài. Dùng 15–20 kỹ năng gộp từ chủ đề Lichess cho mô hình; radar chỉ là lớp hiển thị gom lại |
| "Điểm 72/100" | **Sửa** | Thay bằng rating theo từng chủ đề kèm khoảng tin cậy, để có ý nghĩa thống kê và so được với độ khó bài |
| Lộ trình 14 ngày là "màn hình cốt lõi" | **Đóng khung lại** | Lõi là xếp hạng bài tập; lộ trình là cách gom kết quả theo ngày. Tránh bị xem là trùng nhóm lộ trình học tập |
| BKT | **Giữ, thêm Elo/IRT theo chủ đề** | BKT chỉ biết "đã thành thạo hay chưa", không tính độ khó bài. Elo/IRT dùng được rating Lichess. So hai cái trên dữ liệu thật |
| Next.js, PostgreSQL | **Làm nhẹ lại** | Quá nặng cho 3 người, 3–4 tuần và không được chấm điểm. Chốt React + FastAPI bản nhẹ (Vite, SQLite, parquet; không Next.js, không PostgreSQL), chạy local; Streamlit là phương án dự phòng ([ADR 0001](docs/adr/0001-react-fastapi-thay-streamlit.md)) |
| Knowledge Graph, DKT, RL, gợi ý khai cuộc | **Để hướng phát triển** | Chỉ làm DKT nếu tuần 3 còn thời gian; đồ thị tiên quyết viết tay vài chục cạnh là đủ |
| Không có phần đánh giá | **Thêm (quan trọng nhất)** | Slide chấm "tính đúng đắn của phương pháp" và "chất lượng lập luận". Thiếu số đo thì demo đẹp cũng chỉ là minh họa (mục 7) |
| Từ "lỗi" đến "điểm yếu" | **Thêm kiểm chứng** | 20 ván có thể chỉ có vài lỗi mỗi loại. Cần làm trơn bằng tiên nghiệm (công thức ở mục 6) và cần chứng minh điểm yếu phát hiện được có dự đoán lỗi sau này |

## 6. Phương pháp đề xuất

Hệ thống là một vòng lặp 6 bước; bước 6 đưa kết quả giải bài quay lại bước 3.

Thuật ngữ thống nhất theo [GLOSSARY.md](GLOSSARY.md).

1. **Bản đồ kỹ năng.** Gộp khoảng 60 chủ đề Lichess thành 15–20 kỹ năng, ví dụ: fork, pin, skewer, tấn công phát hiện, quân treo, quân bị nhốt, chiếu hết 1–2 nước, chiếu hết hàng cuối, nước phòng thủ, tàn cuộc tốt, tàn cuộc xe, bỏ lỡ chiến thuật. Mỗi chủ đề thuộc đúng một kỹ năng; motif nhận diện trong ván đi qua cùng bản đồ này. Mỗi bài có vector kỹ năng qᵢ (1 nếu bài thuộc kỹ năng đó). Vài chục cạnh tiên quyết viết tay chỉ làm giảm ưu tiên của kỹ năng sau, không khóa nó.
2. **Phân tích ván và điểm yếu.** Tải ván qua Lichess API và Chess.com API khi người chơi liên kết tài khoản; nút "Cập nhật" chỉ lấy ván mới. Chỉ dùng ván blitz, rapid, classical, bỏ các nước đi khi đồng hồ còn dưới 10 giây. Stockfish đánh giá từng nước của 30–50 ván gần nhất. Lỗi là nước làm xác suất thắng tụt ≥ 20% (mistake trở lên, thang win% của Lichess), bỏ qua các nước khi thế cờ đã thắng hoặc thua sẵn. Với mỗi lỗi, bộ nhận diện motif xem nước đáp tốt nhất của đối thủ (bị fork, bỏ quân treo…) hoặc nước tốt nhất mình bỏ lỡ; cả hai hướng tính vào cùng một kỹ năng. Lỗi không nhận diện được motif thuộc kỹ năng "bỏ lỡ chiến thuật". Giai đoạn ván xác định theo số nước và vật chất còn lại.
3. **Mô hình năng lực.** Mỗi người có năng lực chung θᵤ và độ lệch theo từng kỹ năng θᵤₖ (bắt đầu từ 0, co về 0 khi ít dữ liệu), cùng thang với rating bài tập Lichess ([ADR 0003](docs/adr/0003-theta-tren-thang-rating-bai-lichess.md)). Rating ván chỉ được quy đổi thô thành tiên nghiệm cho θᵤ. Điểm yếu từ ván làm tiên nghiệm cho θᵤₖ đúng một lần lúc khởi tạo; về sau ván mới chỉ thay đổi prioᵤₖ ([ADR 0004](docs/adr/0004-diem-yeu-tu-van-chi-vao-prio.md)). Elo theo kỹ năng chạy trong app; BKT của pyBKT chỉ để so sánh ([ADR 0002](docs/adr/0002-elo-theo-ky-nang-chay-bkt-de-so.md)); DKT nếu kịp.
4. **Bài kiểm tra đầu vào.** 12 bài cố định: chọn 12 kỹ năng phổ biến nhất, mỗi kỹ năng một bài có rating quanh tiên nghiệm θ, chọn trước cho từng dải 200 điểm. Kỹ năng chưa được kiểm tra giữ σ lớn để buổi luyện thăm dò tiếp. Bản thích nghi theo IRT (chọn kỹ năng còn bất định nhất, độ khó sao cho xác suất đúng gần 50%) để ở tuần 4 nếu còn thời gian.
5. **Sinh ứng viên và xếp hạng.** Lọc kho 6 triệu bài: thuộc 5 kỹ năng ưu tiên cao nhất, rating trong khoảng θᵤ ± 300, Popularity và NbPlays đủ cao, chưa làm. Chấm điểm từng bài (công thức dưới), rồi chọn top-K bằng MMR để không dồn một kỹ năng.
6. **Buổi luyện và cập nhật.** 30 phút mỗi ngày ứng với khoảng 15–20 bài: 70% bài mới theo xếp hạng, 20% bài ôn lại (bài mới, chưa làm bao giờ, thuộc kỹ năng vừa giải sai gần đây; không bao giờ đưa lại bài đã làm), 10% bài hỗn hợp. Một lần giải chỉ có đúng/sai: một nước được tính đúng nếu trùng lời giải hoặc chiếu hết, và sai một nước là cả lần giải sai (khớp `is_correct` của bộ Stanford). Sau mỗi bài, θ cập nhật và buổi luyện được tính lại. Lộ trình 14 ngày chỉ là tab xem trước.

**Xác suất giải đúng** (dạng Elo/IRT, bᵢ là rating Lichess của bài, s = 400/ln 10):

```latex
p_{ui} = \sigma\!\left(\frac{\theta_u + \frac{1}{|K_i|}\sum_{k \in K_i} \theta_{uk} - b_i}{s}\right)
```

**Cập nhật sau mỗi lần giải** (y = 1 nếu đúng; Kₖ giảm dần theo số bài đã làm của kỹ năng):

```latex
\theta_u \leftarrow \theta_u + K_g\,(y - p_{ui}), \qquad \theta_{uk} \leftarrow \theta_{uk} + K_k\,(y - p_{ui}) \quad \forall k \in K_i
```

**Điểm yếu từ ván cờ** (tỉ lệ lỗi loại k mỗi ván, co về trung bình μₖ của nhóm tham chiếu, tức người có θ cùng dải 200 điểm, tính từ các tài khoản thu ở lớp 2b; α khoảng 10 ván giả định; người chưa có ván nào thì wᵤₖ = μₖ):

```latex
w_{uk} = \frac{n^{\text{lỗi}}_{uk} + \alpha\,\mu_k}{n^{\text{ván}}_{u} + \alpha}
```

**Điểm gợi ý của bài i** (p\* = 0,7; σᵤₖ là độ bất định của kỹ năng, khuyến khích thăm dò; trọng số λ chọn bằng mô phỏng ở mục 7):

```latex
\text{score}(u,i) = -\lambda_1 \lvert p_{ui} - p^* \rvert + \lambda_2 \max_{k \in K_i} \text{prio}_{uk} + \lambda_3 \max_{k \in K_i} \sigma_{uk} + \lambda_4\, \text{quality}_i
```

Độ ưu tiên prioᵤₖ gộp hai nguồn: kỹ năng thấp hơn mức chung (−θᵤₖ) và hay sai trong ván (wᵤₖ), cộng điểm nếu kỹ năng tiên quyết đã vững. qualityᵢ lấy từ Popularity của Lichess.

**Giải thích theo mẫu**, lấy thẳng từ các thành phần điểm: "Bạn bị fork 6 lần trong 30 ván gần đây, gấp đôi người cùng mức"; "Dự đoán bạn giải đúng 72%"; "Ôn lại: bạn sai bài pin hôm qua".

## 7. Cách đánh giá

Không thể cho người thật học 14 ngày rồi đo Elo, nên đánh giá chia ba lớp, mỗi lớp kiểm tra một khâu của vòng lặp và có baseline rõ.

| Lớp | Kiểm tra khâu nào | Dữ liệu | Cách đo | Baseline |
| --- | --- | --- | --- | --- |
| 1. Dự đoán đúng/sai | Mô hình năng lực có đúng không | Bộ Stanford Chess.com, chia theo thời gian trong từng người (20% lần giải cuối làm test) | Accuracy, AUC, log-loss; độ hiệu chỉnh (calibration) vì hàm chấm điểm dùng xác suất | Elo chung (\~47%), rating Chess.com (\~59%), IRT; so với Elo theo kỹ năng, BKT, DKT nếu kịp |
| 2a. Nhận diện motif | Bộ phân loại lỗi có đúng không | 2.000–5.000 bài Lichess có nhãn Themes | Precision/recall theo từng motif | cook.py vs chess\_detect |
| 2b. Điểm yếu có thật không | Điểm yếu phát hiện từ ván cờ có bền không | 100–200 tài khoản Lichess, chia ván thành giai đoạn trước/sau | Điểm yếu giai đoạn trước dự đoán loại lỗi giai đoạn sau: precision@3, tương quan hạng | Tần suất lỗi chung của mọi người cùng mức Elo |
| 3. Chính sách gợi ý | Chọn bài kiểu nào giúp học nhanh hơn | Người học mô phỏng: vector kỹ năng ẩn lấy từ phân bố ước lượng ở lớp 1; mỗi bài vừa sức làm tăng kỹ năng tương ứng | Mức tăng kỹ năng thật (ẩn) sau 14 ngày × 20 bài; số bài để kỹ năng yếu nhất đạt ngưỡng | Ngẫu nhiên theo rating (kiểu Lichess), chỉ theo điểm yếu, chỉ theo độ vừa sức, bản đầy đủ |

Bốn nguyên tắc để lập luận chặt:

- **Lớp 3 là so sánh tương đối, không phải bằng chứng người thật tiến bộ.** Báo cáo nói thẳng điều này và chạy phân tích độ nhạy: đổi tốc độ học, đổi "vùng vừa sức" của người mô phỏng; chỉ kết luận khi thứ hạng các chính sách không đổi.
- **Người mô phỏng không được dùng chính công thức của hệ gợi ý**, nếu không sẽ tự chấm điểm cho mình. Ví dụ dùng BKT để sinh dữ liệu khi hệ gợi ý dùng Elo theo kỹ năng.
- **Mọi con số chạy 3 seed**, báo trung bình ± độ lệch chuẩn.
- **Case study hai người Elo 1200** đặt sau bảng số: hồ sơ khác nhau, top-10 khác nhau, đo độ trùng (Jaccard) giữa hai danh sách so với baseline chỉ theo rating.

## 8. Phạm vi khả thi 3–4 tuần

3 người làm kịp nếu mỗi người giữ một khâu của vòng lặp và một lớp đánh giá; mốc quan trọng là cuối tuần 2 chạy được trọn vòng cho một người chơi.

| Thành viên | Phụ trách | Lớp đánh giá | Màn hình demo |
| --- | --- | --- | --- |
| A | Dữ liệu bài tập, bản đồ kỹ năng, mô hình năng lực (Elo theo kỹ năng, BKT), bài kiểm tra đầu vào, người học mô phỏng (BKT) | Lớp 1, lớp 3 | Đánh giá đầu vào, hồ sơ kỹ năng |
| B | Tải ván Lichess + Chess.com, Stockfish, nhận diện motif, điểm yếu, nhóm tham chiếu, persona | Lớp 2a, 2b | Phân tích ván |
| C | Sinh ứng viên, hàm chấm điểm, buổi luyện, lộ trình, giải thích; React + FastAPI, đăng nhập email + mật khẩu, job nền | — | Buổi luyện, làm bài và cập nhật, lộ trình |

**Tuần 1: Dữ liệu và baseline**

- [ ] (A) Tải kho Lichess và bộ Stanford; kiểm tra kích thước, giấy phép, tên cột thật
- [ ] (A) Bản đồ 15–20 kỹ năng; chạy Elo chung và IRT trên bộ Stanford
- [ ] (B) Script tải ván qua Lichess API; Stockfish phân tích thử 20 ván, đo thời gian mỗi ván
- [ ] (B) Chạy cook.py và chess\_detect trên vài trăm bài có nhãn
- [ ] (C) Khung React + FastAPI + SQLite: đăng ký/đăng nhập, bàn cờ giải được 1 bài; lọc ứng viên theo kỹ năng và rating

**Tuần 2: Trọn vòng cho một người**

- [ ] (A) Elo theo kỹ năng và BKT, so trên lớp 1; 12 bài kiểm tra đầu vào cố định
- [ ] (B) Điểm yếu từ ván có làm trơn; bảng μₖ theo nhóm tham chiếu; tải ván của 50 tài khoản cho lớp 2b; connector Chess.com
- [ ] (C) Hàm chấm điểm, MMR, giải thích; cập nhật θ sau mỗi bài; job nền đồng bộ ván
- [ ] (Cả nhóm) Chạy trọn vòng ván cờ → hồ sơ → gợi ý → làm bài → cập nhật cho 1 tài khoản

**Tuần 3: Đánh giá, demo, báo cáo**

- [ ] (A) Người học mô phỏng (BKT), so 4 chính sách, phân tích độ nhạy; 3 seed cho lớp 1
- [ ] (B) Lớp 2a, 2b; chọn hai persona Elo 1200 có hồ sơ khác nhau, tạo sẵn tài khoản seed
- [ ] (C) Hoàn thiện các màn hình; tab lộ trình; chạy được khi không có mạng
- [ ] (Cả nhóm) Báo cáo PDF 6 mục (viết song song từ tuần 2), ghi rõ code và dữ liệu dùng lại (cook.py, chess\_detect, pyBKT, Stockfish); slide 15 phút, tổng duyệt 2 lần

**Tuần 4: Đệm**

- [ ] Bù phần trễ; nếu còn thời gian: bài kiểm tra đầu vào thích nghi, DKT, lớp 2b lên 100–200 tài khoản

Nếu tuần 2 bị trễ, cắt theo thứ tự: connector Chess.com (vẫn nạp được PGN) → tab lộ trình → lớp 2b còn 30 tài khoản. Không cắt lớp 1, lớp 3 và vòng lặp lõi. Nếu cuối tuần 2 chưa chạy được trọn vòng thì chuyển giao diện sang Streamlit.

## 9. Rủi ro

Rủi ro lớn nhất là bộ Stanford không dùng được, vì lớp 1 phụ thuộc vào nó; cần biết ngay trong 2 ngày đầu.

| Rủi ro | Dấu hiệu | Dự phòng |
| --- | --- | --- |
| Bộ Stanford không tải được, quá nhỏ hoặc cấm dùng ngoài môn | Link hỏng, ít người dùng, điều khoản hạn chế | Tự thu lịch sử giải bài của nhóm và bạn bè qua app (vài nghìn lần giải); lớp 1 thu nhỏ, dồn trọng tâm sang lớp 2 và 3 |
| Stockfish chậm | Phân tích 1 ván mất hơn 30 giây | Giảm độ sâu, chỉ phân tích kỹ nước có điểm tụt lớn; dùng sẵn đánh giá của Lichess (`evals`) với ván đã được phân tích; chạy trước, lưu cache |
| Nhận diện motif sai nhiều | Precision dưới 60% ở lớp 2a | Chỉ giữ các motif đạt ngưỡng; motif còn lại gộp vào nhóm "bỏ lỡ chiến thuật" |
| Điểm yếu không bền | Lớp 2b không hơn baseline tần suất chung | Vẫn là kết quả đáng báo cáo; tăng trọng số cho kết quả giải bài, giảm cho ván cờ |
| Giảng viên cho là trùng nhóm lộ trình học tập | Câu hỏi khi duyệt đề cương | Proposal nêu rõ item, kho 6 triệu bài, ba lớp đánh giá; gửi sớm để hỏi |
| Giảng viên không chơi cờ | Khó theo dõi demo | Tô màu quân bị tấn công và mũi tên nước đúng; giải thích bằng lời thường ("một quân đánh hai quân cùng lúc"); nhấn mạnh con số và hai danh sách khác nhau |
| Kết quả mô phỏng bị chất vấn | "Người học giả thì đúng công thức của nhóm" | Người mô phỏng dùng mô hình khác hệ gợi ý; phân tích độ nhạy; nói rõ giới hạn trong báo cáo |
| API Lichess giới hạn tốc độ | Lỗi 429 | Tải dần từ tuần 1, lưu file; demo không gọi API |

## 10. Nguồn tham khảo

- [Lichess open database – puzzles](https://database.lichess.org/) ([file CSV](https://database.lichess.org/lichess_db_puzzle.csv.zst))
- [Lichess API – export games of a user](https://lichess.org/api#tag/Games/operation/apiGamesUser)
- [Stanford CS398 – Chess.com Knowledge Tracing](https://web.stanford.edu/class/cs398/handouts/knowledge-tracing.html) ([starter bundle](https://web.stanford.edu/class/cs398/handouts/knowledge-tracing/starter_bundle.zip))
- [Nie và cộng sự – Discovering High Quality Chess Puzzles with Offline Reinforcement Learning (RLC 2026)](https://rlj.cs.umass.edu/2026/papers/Paper147.html)
- [ExRec – arXiv 2507.11060](https://arxiv.org/abs/2507.11060)
- [Maia-2 – arXiv 2409.20553](https://arxiv.org/abs/2409.20553) · [code](https://github.com/CSSLab/maia2)
- [pyBKT](https://github.com/CAHLR/pyBKT)
- [lichess-puzzler, tagger/cook.py](https://github.com/ornicar/lichess-puzzler/blob/d02e3600671c2b4499b5bd179658813a4ade1452/tagger/cook.py)
- [chess\_detect](https://github.com/aslyamov/chess_detect) · [PyPI](https://pypi.org/project/chess-detect/)
- [ChessPuzzleKit](https://pypi.org/project/ChessPuzzleKit/)
- Piech và cộng sự, Deep Knowledge Tracing, NeurIPS 2015 (trích theo trí nhớ, chưa mở lại trang gốc)
