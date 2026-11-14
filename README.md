# chesscoach

Hệ gợi ý bài tập cờ vua cá nhân hóa: chọn bài tập vừa sức, nhắm vào điểm yếu của từng người chơi. Thuật ngữ xem [GLOSSARY.md](GLOSSARY.md), các quyết định kiến trúc xem [docs/adr/](docs/adr/).

## Chạy trên máy local

Cần [uv](https://docs.astral.sh/uv/) và Node.js 20+.

```sh
npm install        # cài concurrently ở thư mục gốc
npm run setup      # cài phụ thuộc backend (uv) và frontend (npm)
cp backend/.env.example backend/.env   # rồi điền LICHESS_API_TOKEN
```

Nạp kho bài tập Lichess (CC0, khoảng 300 MB tải về, 6,2 triệu bài tập) một lần:

```sh
cd backend
mkdir -p data/raw
curl -o data/raw/lichess_db_puzzle.csv.zst https://database.lichess.org/lichess_db_puzzle.csv.zst
uv run python -m chesscoach.puzzle_import full data/raw/lichess_db_puzzle.csv.zst data/puzzles.parquet
cd ..
```

Sau đó chạy:

```sh
npm run dev        # chạy FastAPI ở :8000 và Vite ở :5173
```

Mở http://localhost:5173. Vite chuyển các request `/api` sang FastAPI, nên cookie phiên đăng nhập luôn cùng origin với trang.

Dữ liệu lưu trong `backend/data/` (đã nằm trong `.gitignore`): `chesscoach.db` cho người chơi và lần giải, `puzzles.parquet` cho kho bài tập. Muốn đổi đường dẫn thì xem `backend/.env.example`.

Test dùng bản mẫu 300 bài tập trong `backend/tests/fixtures/puzzles_sample.csv`, nên không cần nạp kho đầy đủ. Bản mẫu được sinh bằng `puzzle_import sample` và tái lập được: cùng seed thì ra đúng bộ bài tập đó.

## Kiểm thử

```sh
npm test           # pytest: test gọi HTTP API với SQLite trong bộ nhớ
npm run typecheck  # mypy (strict) cho backend, tsc cho frontend
```
