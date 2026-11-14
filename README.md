# chesscoach

Hệ gợi ý bài tập cờ vua cá nhân hóa: chọn bài tập vừa sức, nhắm vào điểm yếu của từng người chơi. Thuật ngữ xem [GLOSSARY.md](GLOSSARY.md), các quyết định kiến trúc xem [docs/adr/](docs/adr/).

## Chạy trên máy local

Cần [uv](https://docs.astral.sh/uv/) và Node.js 20+.

```sh
npm install        # cài concurrently ở thư mục gốc
npm run setup      # cài phụ thuộc backend (uv) và frontend (npm)
npm run dev        # chạy FastAPI ở :8000 và Vite ở :5173
```

Mở http://localhost:5173. Vite chuyển các request `/api` sang FastAPI, nên cookie phiên đăng nhập luôn cùng origin với trang.

Dữ liệu lưu trong `backend/data/chesscoach.db`. Muốn dùng file khác thì đặt biến `CHESSCOACH_DATABASE_URL`.

## Kiểm thử

```sh
npm test           # pytest: test gọi HTTP API với SQLite trong bộ nhớ
npm run typecheck  # mypy (strict) cho backend, tsc cho frontend
```
