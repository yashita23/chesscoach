from fastapi.testclient import TestClient
from helpers import play, start

# Bài 0VN0C (rating 1699): người chơi cầm trắng, đi 3 nước d6d7, d4d7, g7e5.
# Moves: e8e7 d6d7 f6d7 d4d7 e7d7 g7e5
LONG_PUZZLE = "0VN0C"
LONG_PUZZLE_FEN = "r3k1n1/pp3pQ1/3Rpnp1/4q3/2PR4/1P5P/P5P1/6K1 b q - 4 30"

# Bài BXfU5 (mateIn1): lời giải là h4h1, nhưng h4h2 cũng chiếu hết.
MATE_PUZZLE = "BXfU5"

# Bài 9v8Hb: người chơi cầm đen; Moves a7b7 b8b7 f7f8q c2c1q (phong hậu ở nước cuối).
PROMOTION_PUZZLE = "9v8Hb"


def test_bat_dau_lan_giai_thi_doi_thu_da_di_nuoc_dau(player: TestClient) -> None:
    attempt = start(player, LONG_PUZZLE)

    assert attempt["puzzle_id"] == LONG_PUZZLE
    assert attempt["start_fen"] == LONG_PUZZLE_FEN
    assert attempt["opponent_move"] == "e8e7"
    assert attempt["fen"].startswith("r5n1/pp2kpQ1/3Rpnp1/")
    assert attempt["player_color"] == "white"


def test_nuoc_chieu_het_khac_loi_giai_van_tinh_dung(player: TestClient) -> None:
    attempt = start(player, MATE_PUZZLE)

    result = play(player, attempt["attempt_id"], "h4h2")

    assert result["verdict"] == "correct"
    assert result["completed"] is True
    assert result["correct"] is True


def test_sai_nuoc_thu_hai_thi_lan_giai_sai_va_di_tiep_loi_giai_khong_doi_nhan(
    player: TestClient,
) -> None:
    attempt_id = start(player, LONG_PUZZLE)["attempt_id"]

    first = play(player, attempt_id, "d6d7")
    assert (first["verdict"], first["opponent_move"], first["correct"]) == ("correct", "f6d7", None)

    wrong = play(player, attempt_id, "g7h8")
    assert wrong["verdict"] == "wrong"
    assert wrong["expected_move"] == "d4d7"
    assert wrong["correct"] is False
    assert wrong["completed"] is False

    play(player, attempt_id, "d4d7")
    last = play(player, attempt_id, "g7e5")
    assert last["verdict"] == "correct"
    assert last["completed"] is True
    assert last["correct"] is False


def test_phong_cap_dung_quan_trong_loi_giai_thi_dung(player: TestClient) -> None:
    attempt_id = start(player, PROMOTION_PUZZLE)["attempt_id"]
    play(player, attempt_id, "b8b7")

    result = play(player, attempt_id, "c2c1q")

    assert (result["verdict"], result["completed"], result["correct"]) == ("correct", True, True)


def test_phong_cap_sai_quan_thi_sai(player: TestClient) -> None:
    attempt_id = start(player, PROMOTION_PUZZLE)["attempt_id"]
    play(player, attempt_id, "b8b7")

    result = play(player, attempt_id, "c2c1n")

    assert (result["verdict"], result["expected_move"], result["correct"]) == ("wrong", "c2c1q", False)


def test_nuoc_khong_hop_le_bi_tu_choi_va_khong_tinh_la_sai(player: TestClient) -> None:
    attempt_id = start(player, LONG_PUZZLE)["attempt_id"]

    for uci in ("d6d9", "xyz", "a2a5"):
        r = player.post(f"/api/attempts/{attempt_id}/moves", json={"uci": uci})
        assert r.status_code == 422, uci

    assert play(player, attempt_id, "d6d7")["correct"] is None


def test_lan_giai_da_xong_khong_nhan_them_nuoc(player: TestClient) -> None:
    attempt_id = start(player, MATE_PUZZLE)["attempt_id"]
    play(player, attempt_id, "h4h1")

    r = player.post(f"/api/attempts/{attempt_id}/moves", json={"uci": "h1h2"})

    assert r.status_code == 409


def test_khong_dung_duoc_lan_giai_cua_nguoi_khac(player: TestClient) -> None:
    attempt_id = start(player, MATE_PUZZLE)["attempt_id"]
    player.post("/api/auth/logout")
    player.post(
        "/api/auth/register",
        json={"email": "khac@example.com", "password": "matkhau-dai-du", "display_name": "Khác"},
    )

    r = player.post(f"/api/attempts/{attempt_id}/moves", json={"uci": "h4h1"})

    assert r.status_code == 404
    assert player.get("/api/attempts").json() == []


def test_bai_tap_khong_ton_tai_tra_404(player: TestClient) -> None:
    r = player.post("/api/attempts", json={"puzzle_id": "khong-co"})

    assert r.status_code == 404


def test_mo_lai_bai_tap_dang_do_thi_tiep_tuc_dung_lan_giai_do(player: TestClient) -> None:
    attempt_id = start(player, LONG_PUZZLE)["attempt_id"]
    after_first = play(player, attempt_id, "d6d7")

    assert player.get("/api/puzzles/next").json()["puzzle_id"] == LONG_PUZZLE
    resumed = player.post("/api/attempts", json={"puzzle_id": LONG_PUZZLE})

    assert resumed.status_code == 200
    body = resumed.json()
    assert body["attempt_id"] == attempt_id
    assert body["fen"] == after_first["fen"]
    assert body["opponent_move"] == "f6d7"
    assert play(player, attempt_id, "d4d7")["verdict"] == "correct"
    assert len(player.get("/api/attempts").json()) == 1


def test_bai_tap_da_co_nhan_khong_mo_lai_duoc(player: TestClient) -> None:
    attempt_id = start(player, LONG_PUZZLE)["attempt_id"]
    play(player, attempt_id, "g7h7")  # sai ngay nước đầu: nhãn đã chốt, chưa đi hết lời giải

    r = player.post("/api/attempts", json={"puzzle_id": LONG_PUZZLE})

    assert r.status_code == 409
    assert player.get("/api/puzzles/next").json()["puzzle_id"] != LONG_PUZZLE


def test_bai_tap_tiep_theo_mo_duoc_lan_giai_moi(player: TestClient) -> None:
    puzzle_id = player.get("/api/puzzles/next").json()["puzzle_id"]

    r = player.post("/api/attempts", json={"puzzle_id": puzzle_id})

    assert r.status_code == 201


def test_lich_su_luu_bai_tap_thoi_diem_nhan_va_thoi_gian_giai(player: TestClient) -> None:
    long_attempt = start(player, LONG_PUZZLE)["attempt_id"]
    for uci in ("d6d7", "d4d7", "g7e5"):
        play(player, long_attempt, uci)
    mate_attempt = start(player, MATE_PUZZLE)["attempt_id"]
    play(player, mate_attempt, "h4h1")

    history = player.get("/api/attempts").json()

    assert [(a["puzzle_id"], a["correct"]) for a in history] == [
        (MATE_PUZZLE, True),
        (LONG_PUZZLE, True),
    ]
    for a in history:
        assert a["started_at"].endswith(("Z", "+00:00"))
        assert a["solve_time_ms"] >= 0
