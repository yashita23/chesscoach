# chesscoach

Hệ gợi ý bài tập cờ vua cá nhân hóa: chọn bài tập vừa sức, nhắm vào điểm yếu của từng người chơi. Thuật ngữ xem [GLOSSARY.md](GLOSSARY.md), các quyết định kiến trúc xem [docs/adr/](docs/adr/).

## Chạy trên máy local

Cần [uv](https://docs.astral.sh/uv/) và Node.js 20+.

```sh
npm install        # cài concurrently ở thư mục gốc
npm run setup      # cài phụ thuộc backend (uv) và frontend (npm)
cp backend/.env.example backend/.env   # rồi điền LICHESS_API_TOKEN
```

Tải dữ liệu một lần (khoảng 340 MB, vài phút):

```sh
npm run data       # kho bài tập Lichess + bộ Stanford Chess.com, dựng parquet và phép chia
```

Dữ liệu **không nằm trong git**. Repo để công khai, kho Lichess nặng hơn giới hạn 100 MB của GitHub, và bộ Stanford không có giấy phép phân phối lại. Vì vậy mỗi người tự tải từ nguồn gốc. Mọi bước đều cho ra đúng một kết quả, nên máy ai cũng có cùng kho bài tập (6,2 triệu bài tập, CC0) và cùng phép chia Stanford. Bước nào đã có kết quả thì được bỏ qua; muốn làm lại từ đầu thì chạy `npm run data -- --force`.

Sau đó chạy:

```sh
npm run dev        # chạy FastAPI ở :8000 và Vite ở :5173
```

Mở http://localhost:5173. Vite chuyển các request `/api` sang FastAPI, nên cookie phiên đăng nhập luôn cùng origin với trang.

Dữ liệu lưu trong `backend/data/` (đã nằm trong `.gitignore`):
- `chesscoach.db`: người chơi và lần giải;
- `puzzles.parquet`: kho bài tập;
- `stanford/`: bộ dữ liệu cho lớp đánh giá 1, xem [docs/experiments/e0-stanford.md](docs/experiments/e0-stanford.md).

Muốn đổi đường dẫn thì xem `backend/.env.example`.

Test dùng bản mẫu 300 bài tập trong `backend/tests/fixtures/puzzles_sample.csv`, nên không cần nạp kho đầy đủ. Bản mẫu được sinh bằng `puzzle_import sample` và tái lập được: cùng seed thì ra đúng bộ bài tập đó.

## Kiểm thử

```sh
npm test           # pytest: test gọi HTTP API với SQLite trong bộ nhớ
npm run typecheck  # mypy (strict) cho backend, tsc cho frontend
```
