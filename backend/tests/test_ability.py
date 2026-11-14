from typing import Any

from fastapi.testclient import TestClient
from helpers import play, start

# Bài tập GqnTb (rating 1539): chỉ có kỹ năng fork. Lời giải d1a4 … a4b4; c4e6 là nước sai.
FORK_PUZZLE = "GqnTb"
# Bài tập 0VN0C (rating 1699).
PUZZLE_1699 = "0VN0C"


def profile(client: TestClient) -> dict[str, Any]:
    r = client.get("/api/profile")
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def skill(prof: dict[str, Any], skill_id: str) -> dict[str, Any]:
    found: dict[str, Any] = next(s for s in prof["skills"] if s["id"] == skill_id)
    return found


def test_nguoi_choi_moi_du_doan_theo_cong_thuc_elo(player: TestClient) -> None:
    # θ = 1500, mọi độ lệch kỹ năng = 0: p = 1 / (1 + 10^((1699 - 1500) / 400)) ≈ 0.2413
    attempt = start(player, PUZZLE_1699)

    assert abs(attempt["predicted_p"] - 0.2413) < 1e-3


def test_ho_so_nguoi_choi_moi_chua_du_du_lieu(player: TestClient) -> None:
    prof = profile(player)

    assert prof["theta"] == 1500
    assert prof["attempts"] == 0
    assert 15 <= len(prof["skills"]) <= 20
    assert all(not s["enough_data"] for s in prof["skills"])
    assert all(g["ability"] is None for g in prof["groups"])
    grouped = sorted(skill_id for g in prof["groups"] for skill_id in g["skills"])
    assert grouped == sorted(s["id"] for s in prof["skills"])  # mỗi kỹ năng thuộc đúng một nhóm radar


def test_giai_dung_bai_tap_fork_thi_nang_luc_fork_tang_ky_nang_khac_giu_nguyen(
    player: TestClient,
) -> None:
    before = profile(player)
    attempt_id = start(player, FORK_PUZZLE)["attempt_id"]
    play(player, attempt_id, "d1a4")
    assert play(player, attempt_id, "a4b4")["correct"] is True

    after = profile(player)

    assert skill(after, "fork")["ability"] > skill(before, "fork")["ability"]
    assert skill(after, "fork")["deviation"] > 0
    assert skill(after, "fork")["attempts"] == 1
    assert skill(after, "fork")["enough_data"] is True
    assert skill(after, "rook_endgame")["deviation"] == 0
    assert skill(after, "rook_endgame")["attempts"] == 0


def test_giai_sai_bai_tap_fork_thi_nang_luc_fork_giam(player: TestClient) -> None:
    before = profile(player)
    attempt_id = start(player, FORK_PUZZLE)["attempt_id"]
    assert play(player, attempt_id, "c4e6")["correct"] is False

    after = profile(player)

    assert skill(after, "fork")["ability"] < skill(before, "fork")["ability"]
    assert skill(after, "fork")["deviation"] < 0
    assert skill(after, "pin")["deviation"] == 0


def test_khoang_tin_cay_hep_lai_sau_moi_lan_giai(player: TestClient) -> None:
    def width(prof: dict[str, Any]) -> float:
        s = skill(prof, "fork")
        return float(s["ci"]["high"] - s["ci"]["low"])

    before = profile(player)
    attempt_id = start(player, FORK_PUZZLE)["attempt_id"]
    play(player, attempt_id, "c4e6")

    assert width(profile(player)) < width(before)


def test_du_doan_doi_theo_nang_luc_sau_lan_giai(player: TestClient) -> None:
    p_before = start(player, PUZZLE_1699)["predicted_p"]
    fork_attempt = start(player, FORK_PUZZLE)["attempt_id"]
    play(player, fork_attempt, "d1a4")
    play(player, fork_attempt, "a4b4")

    # Mở lại lần giải 0VN0C đang dở: năng lực chung đã tăng nên dự đoán cao hơn.
    assert start_again(player, PUZZLE_1699)["predicted_p"] > p_before


def start_again(client: TestClient, puzzle_id: str) -> dict[str, Any]:
    r = client.post("/api/attempts", json={"puzzle_id": puzzle_id})
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body
