"""Gọi API dùng chung cho các test."""

from typing import Any

from fastapi.testclient import TestClient


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
