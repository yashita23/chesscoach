from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chesscoach.app import create_app

# 300 bài thật lấy từ kho Lichess (CC0) bằng `puzzle_import sample`.
PUZZLE_SAMPLE = Path(__file__).parent / "fixtures" / "puzzles_sample.csv"


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(database_url="sqlite:///:memory:", puzzle_catalog=PUZZLE_SAMPLE)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def player(client: TestClient) -> TestClient:
    """Client đã đăng nhập sẵn một người chơi."""
    r = client.post(
        "/api/auth/register",
        json={"email": "giai@example.com", "password": "matkhau-dai-du", "display_name": "Giải"},
    )
    assert r.status_code == 201, r.text
    return client
