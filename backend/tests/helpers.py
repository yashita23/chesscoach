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
