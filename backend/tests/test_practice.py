import csv
from collections import Counter
from collections.abc import Iterator
from typing import Any

import chess
from conftest import PUZZLE_SAMPLE
from fastapi.testclient import TestClient
from helpers import play, register_new_player, start

from chesscoach.app import create_app
from chesscoach.recommend import PracticeConfig


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


def me(client: TestClient) -> dict[str, Any]:
    body: dict[str, Any] = client.get("/api/me").json()
    return body


def test_nguoi_choi_khai_va_sua_thoi_gian_luyen_moi_ngay(player: TestClient) -> None:
    assert me(player)["daily_minutes"] == 30  # mặc định

    r = player.patch("/api/me", json={"daily_minutes": 45})

    assert r.status_code == 200
    assert me(player)["daily_minutes"] == 45


def test_thoi_gian_luyen_ngoai_khoang_hop_le_bi_tu_choi(player: TestClient) -> None:
    for minutes in (0, 2, 500):
        assert player.patch("/api/me", json={"daily_minutes": minutes}).status_code == 422, minutes

    assert me(player)["daily_minutes"] == 30


def practice(client: TestClient) -> dict[str, Any]:
    r = client.get("/api/practice")
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def test_buoi_luyen_30_phut_co_15_den_20_bai_tap_va_du_thong_tin(player: TestClient) -> None:
    s = practice(player)

    assert 15 <= len(s["items"]) <= 20
    item = s["items"][0]
    assert {"puzzle_id", "fen", "player_color", "rating", "predicted_p", "skills", "score"} <= item.keys()
    assert {"total", "fit", "exploration", "quality"} <= item["score"].keys()
    assert item["player_color"] in ("white", "black")
    assert item["skills"]


def test_it_thoi_gian_thi_buoi_luyen_ngan_hon(player: TestClient) -> None:
    player.patch("/api/me", json={"daily_minutes": 10})

    assert len(practice(player)["items"]) < 15


def test_buoi_luyen_khong_bao_gio_chua_bai_tap_da_lam(player: TestClient) -> None:
    done = []
    for item in practice(player)["items"][:5]:
        start(player, item["puzzle_id"])  # lần giải mở nhưng chưa có nhãn
        done.append(item["puzzle_id"])
    labeled = practice(player)["items"][0]["puzzle_id"]
    finish_wrong(player, labeled)
    done.append(labeled)

    assert not set(done) & {i["puzzle_id"] for i in practice(player)["items"]}


def test_xac_suat_du_doan_quanh_0_7(player: TestClient) -> None:
    ps = [i["predicted_p"] for i in practice(player)["items"]]

    assert all(0.55 <= p <= 0.85 for p in ps), ps
    assert abs(sum(ps) / len(ps) - 0.7) < 0.05


def test_khong_ky_nang_nao_vuot_40_phan_tram_buoi_luyen(player: TestClient) -> None:
    items = practice(player)["items"]
    counts = Counter(skill["id"] for i in items for skill in i["skills"])

    assert max(counts.values()) <= 0.4 * len(items), counts


def test_buoi_luyen_giu_nguyen_khi_chua_giai_va_doi_sau_moi_lan_giai(player: TestClient) -> None:
    first = [i["puzzle_id"] for i in practice(player)["items"]]
    assert [i["puzzle_id"] for i in practice(player)["items"]] == first

    finish_wrong(player, first[0])
    after = [i["puzzle_id"] for i in practice(player)["items"]]

    assert first[0] not in after
    assert after != first[1:]  # tính lại toàn bộ, không chỉ bỏ bài tập vừa giải


def test_bai_tap_tiep_theo_la_bai_tap_dau_cua_buoi_luyen(player: TestClient) -> None:
    first = practice(player)["items"][0]["puzzle_id"]

    assert player.get("/api/puzzles/next").json()["puzzle_id"] == first


def practice_client(config: PracticeConfig) -> Iterator[TestClient]:
    app = create_app(database_url="sqlite:///:memory:", puzzle_catalog=PUZZLE_SAMPLE, practice_config=config)
    with TestClient(app) as c:
        register_new_player(c, "cau-hinh@example.com")
        yield c


def test_ham_cham_diem_giu_p_quanh_0_7_ca_khi_khoang_rating_rat_rong() -> None:
    # Khoảng rating rộng tới mức gần như cả bản mẫu là ứng viên: chỉ hàm chấm điểm mới giữ được p quanh 0,7.
    for client in practice_client(PracticeConfig(window=3000)):
        ps = [i["predicted_p"] for i in practice(client)["items"]]

        assert abs(sum(ps) / len(ps) - 0.7) < 0.05, ps
        assert all(0.5 <= p <= 0.9 for p in ps), ps


def test_gioi_han_ty_le_ky_nang_doc_tu_cau_hinh() -> None:
    # Tắt MMR để chỉ còn giới hạn tỉ lệ giữ cho buổi luyện đa dạng.
    for client in practice_client(PracticeConfig(window=3000, mmr_lambda=1.0, max_skill_share=0.2)):
        items = practice(client)["items"]
        counts = Counter(skill["id"] for i in items for skill in i["skills"])

        assert max(counts.values()) <= 0.2 * len(items), counts


def distinct_skills(config: PracticeConfig) -> int:
    for client in practice_client(config):
        return len({skill["id"] for i in practice(client)["items"] for skill in i["skills"]})
    raise AssertionError("không tạo được client")


def test_mmr_lam_buoi_luyen_phu_nhieu_ky_nang_hon() -> None:
    # Bỏ giới hạn tỉ lệ kỹ năng để chỉ so tác dụng của MMR.
    with_mmr = distinct_skills(PracticeConfig(window=3000, max_skill_share=1.0))
    without_mmr = distinct_skills(PracticeConfig(window=3000, max_skill_share=1.0, mmr_lambda=1.0))

    assert with_mmr >= without_mmr + 3, (with_mmr, without_mmr)


def test_nang_luc_rat_thap_van_co_buoi_luyen(player: TestClient) -> None:
    # Giải sai liên tục cho tới khi rating mục tiêu thấp hơn mọi bài tập của bản mẫu (thấp nhất 481) quá 300.
    for _ in range(40):
        current = practice(player)
        if current["target_rating"] < 481 - 300:
            break
        finish_wrong(player, current["items"][0]["puzzle_id"])
    assert current["target_rating"] < 481 - 300

    assert len(practice(player)["items"]) >= 3
