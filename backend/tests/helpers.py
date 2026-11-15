"""Gọi API dùng chung cho các test."""

import csv
from pathlib import Path
from typing import Any

import chess
from fastapi.testclient import TestClient

PUZZLE_SAMPLE = Path(__file__).parent / "fixtures" / "puzzles_sample.csv"


def start(client: TestClient, puzzle_id: str) -> dict[str, Any]:
    r = client.post("/api/attempts", json={"puzzle_id": puzzle_id})
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


def play(client: TestClient, attempt_id: int, uci: str) -> dict[str, Any]:
    r = client.post(f"/api/attempts/{attempt_id}/moves", json={"uci": uci})
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def register_new_player(client: TestClient, email: str) -> None:
    """Đăng xuất người chơi hiện tại (nếu có) rồi đăng ký và đăng nhập một người chơi mới."""
    client.cookies.clear()
    r = client.post("/api/auth/register", json={"email": email, "password": "matkhau-dai-du", "display_name": "X"})
    assert r.status_code == 201, r.text


def wrong_move(puzzle_id: str) -> str:
    """Một nước hợp lệ, khác lời giải và không chiếu hết, cho nước đầu của người chơi."""
    row = next(r for r in csv.DictReader(PUZZLE_SAMPLE.open(encoding="utf-8")) if r["PuzzleId"] == puzzle_id)
    moves = row["Moves"].split()
    board = chess.Board(row["FEN"])
    board.push_uci(moves[0])
    for move in board.legal_moves:
        board.push(move)
        mate = board.is_checkmate()
        board.pop()
        if move.uci() != moves[1] and not mate:
            return move.uci()
    raise AssertionError(f"bài tập {puzzle_id} không có nước sai phù hợp")


def finish_wrong(client: TestClient, puzzle_id: str) -> None:
    """Mở lần giải rồi đi sai ngay nước đầu: lần giải có nhãn sai."""
    attempt = start(client, puzzle_id)
    assert play(client, attempt["attempt_id"], wrong_move(puzzle_id))["correct"] is False
