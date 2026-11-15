"""Tải và dựng toàn bộ dữ liệu local: kho bài tập Lichess và bộ Stanford Chess.com.

    npm run data                      # ở thư mục gốc
    uv run python -m chesscoach.data_setup [--force] [--data-dir DIR]

Dữ liệu không nằm trong git (repo công khai; kho Lichess hơn 100 MB; bộ Stanford không có giấy phép
phân phối lại), nên mỗi người tự tải từ nguồn gốc. Mọi bước đều tất định: chạy trên máy nào cũng ra cùng
kho bài tập và cùng phép chia. Bước nào đã có kết quả thì bỏ qua, trừ khi có --force. File tải gốc (.zst, .zip)
bị xóa sau khi dựng xong để đỡ tốn ổ đĩa, trừ khi có --keep-raw.
"""

import argparse
import shutil
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

from chesscoach.experiments.stanford import DEFAULT_SEED, make_split
from chesscoach.puzzle_import import import_full

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LICHESS_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"
STANFORD_URL = "https://web.stanford.edu/class/cs398/handouts/knowledge-tracing/starter_bundle.zip"
STANFORD_FILES = ("train.csv", "test.csv", "puzzles.csv", "README.md")


def download(url: str, target: Path) -> None:
    """Tải về file tạm rồi mới đổi tên, để lần tải dở không bị coi là đã xong."""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "chesscoach-data-setup"})
    with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done, last = 0, 0.0
        while chunk := response.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if time.monotonic() - last > 1 or done == total:
                last = time.monotonic()
                share = f" ({done / total:.0%})" if total else ""
                print(f"\r  {done / 1e6:,.0f} MB{share}", end="", flush=True)
    print()
    partial.replace(target)


def safe_extract(archive: Path, target_dir: Path) -> None:
    """Giải nén, từ chối mọi đường dẫn thoát ra ngoài thư mục đích."""
    root = target_dir.resolve()
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            destination = (root / info.filename).resolve()
            if destination != root and root not in destination.parents:
                raise ValueError(f"File nén có đường dẫn lạ: {info.filename}")
        z.extractall(root)


def setup_lichess(data_dir: Path, force: bool, keep_raw: bool) -> None:
    raw = data_dir / "raw" / "lichess_db_puzzle.csv.zst"
    parquet = data_dir / "puzzles.parquet"
    if not force and parquet.exists():
        print(f"Đã có {parquet}, bỏ qua")
        return
    if force or not raw.exists():
        print(f"Tải kho bài tập Lichess (khoảng 300 MB) từ {LICHESS_URL}")
        download(LICHESS_URL, raw)
    print("Dựng puzzles.parquet …")
    print(f"  {import_full(raw, parquet):,} bài tập")
    if not keep_raw:
        raw.unlink()


def setup_stanford(data_dir: Path, force: bool, seed: int, keep_raw: bool) -> None:
    stanford = data_dir / "stanford"
    archive, raw, split = stanford / "starter_bundle.zip", stanford / "raw", stanford / "split"
    if force or not all((raw / name).exists() for name in STANFORD_FILES):
        if force or not archive.exists():
            print(f"Tải bộ Stanford CS398 (khoảng 32 MB) từ {STANFORD_URL}")
            download(STANFORD_URL, archive)
        if raw.exists():
            shutil.rmtree(raw)
        raw.mkdir(parents=True)
        safe_extract(archive, raw)
        if not keep_raw:
            archive.unlink()
    if force or not (split / "manifest.json").exists():
        print(f"Chia bộ Stanford theo thời gian (seed {seed}) …")
        counts = make_split(raw_dir=raw, out_dir=split, seed=seed)
        print(f"  train {counts['train']:,}, test {counts['test']:,} lần giải")
    else:
        print(f"Đã có {split}, bỏ qua")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # console Windows mặc định cp1258
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--force", action="store_true", help="tải và dựng lại mọi bước")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="seed của phép chia Stanford")
    parser.add_argument("--keep-raw", action="store_true", help="giữ file tải gốc (.zst, .zip) sau khi dựng xong")
    args = parser.parse_args()

    setup_lichess(args.data_dir, args.force, args.keep_raw)
    setup_stanford(args.data_dir, args.force, args.seed, args.keep_raw)
    print(f"Xong. Dữ liệu nằm trong {args.data_dir}")


if __name__ == "__main__":
    main()
