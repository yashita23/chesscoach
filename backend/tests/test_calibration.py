import csv
from collections.abc import Iterator

import chess
import pytest
from conftest import PUZZLE_SAMPLE
from fastapi.testclient import TestClient
from helpers import play, start

from chesscoach.app import create_app

MIN_ATTEMPTS = 20


def register(client: TestClient, email: str) -> None:
    client.cookies.clear()
    r = client.post("/api/auth/register", json={"email": email, "password": "matkhau-dai-du", "display_name": "X"})
    assert r.status_code == 201, r.text


def easy_puzzles() -> list[tuple[str, int, str]]:
    """(id, rating, một nước sai hợp lệ không chiếu hết) của các bài tập rating dưới 1300 trong bản mẫu."""
    out = []
    for row in csv.DictReader(PUZZLE_SAMPLE.open(encoding="utf-8")):
        if int(row["Rating"]) >= 1300:
            continue
        moves = row["Moves"].split()
        board = chess.Board(row["FEN"])
        board.push_uci(moves[0])
        for move in board.legal_moves:
            board.push(move)
            mate = board.is_checkmate()
            board.pop()
            if move.uci() != moves[1] and not mate:
                out.append((row["PuzzleId"], int(row["Rating"]), move.uci()))
                break
    return out


def elo_p(rating: int, theta: float = 1500) -> float:
    """Công thức gốc, tính độc lập với code: 1 / (1 + 10^((rating − θ) / 1200)), thang s gấp 3 lần Elo (E1b)."""
    return 1 / (1 + 10 ** ((rating - theta) / 1200))


@pytest.fixture
def calibrating_client() -> Iterator[TestClient]:
    app = create_app(
        database_url="sqlite:///:memory:", puzzle_catalog=PUZZLE_SAMPLE, calibration_min_attempts=MIN_ATTEMPTS
    )
    with TestClient(app) as c:
        yield c


def test_chua_du_lan_giai_thi_xac_suat_giu_cong_thuc_goc(calibrating_client: TestClient) -> None:
    puzzles = easy_puzzles()
    register(calibrating_client, "a@example.com")
    for puzzle_id, _, wrong in puzzles[: MIN_ATTEMPTS - 1]:
        play(calibrating_client, start(calibrating_client, puzzle_id)["attempt_id"], wrong)

    register(calibrating_client, "moi@example.com")
    puzzle_id, rating, _ = puzzles[MIN_ATTEMPTS]

    assert abs(start(calibrating_client, puzzle_id)["predicted_p"] - elo_p(rating)) < 1e-3


def test_hay_giai_sai_bai_tap_duoc_doan_de_thi_xac_suat_duoc_ha_xuong(calibrating_client: TestClient) -> None:
    puzzles = easy_puzzles()
    assert len(puzzles) > MIN_ATTEMPTS + 2
    register(calibrating_client, "a@example.com")
    for puzzle_id, _, wrong in puzzles[:MIN_ATTEMPTS]:
        play(calibrating_client, start(calibrating_client, puzzle_id)["attempt_id"], wrong)

    register(calibrating_client, "moi@example.com")
    puzzle_id, rating, _ = puzzles[MIN_ATTEMPTS + 1]

    # Hướng là điều được kiểm tra; mức hạ nhỏ vì 20 lần giải còn ít so với phần kéo về (a = 0, b = 1).
    assert start(calibrating_client, puzzle_id)["predicted_p"] < elo_p(rating) - 0.01
