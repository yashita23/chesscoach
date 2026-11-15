import csv
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from helpers import PUZZLE_SAMPLE, finish_wrong, register_new_player, start
from fastapi.testclient import TestClient

from chesscoach.app import create_app

PLACEMENT_SAMPLE = Path(__file__).parent / "fixtures" / "placement_sample.json"
SETS = json.loads(PLACEMENT_SAMPLE.read_text(encoding="utf-8"))["sets"]
RATINGS = {r["PuzzleId"]: int(r["Rating"]) for r in csv.DictReader(PUZZLE_SAMPLE.open(encoding="utf-8"))}


@pytest.fixture
def placement_client() -> Iterator[TestClient]:
    app = create_app(database_url="sqlite:///:memory:", puzzle_catalog=PUZZLE_SAMPLE, placement_sets=PLACEMENT_SAMPLE)
    with TestClient(app) as c:
        register_new_player(c, "moi@example.com")
        yield c


def practice(client: TestClient) -> dict[str, Any]:
    r = client.get("/api/practice")
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def placement_ids(body: dict[str, Any]) -> list[str]:
    return [i["puzzle_id"] for i in body["items"]]


def test_nguoi_choi_moi_nhan_bai_kiem_tra_dau_vao_truoc_buoi_luyen(placement_client: TestClient) -> None:
    body = practice(placement_client)

    assert body["mode"] == "placement"
    # Không khai rating ván: tiên nghiệm 1500, dải 1400–1600.
    assert placement_ids(body) == [p["puzzle_id"] for p in SETS["1400"]]
    assert body["placement"] == {"total": len(SETS["1400"]), "completed": 0, "started": False}
    assert placement_client.get("/api/puzzles/next").json()["puzzle_id"] == SETS["1400"][0]["puzzle_id"]


def test_rating_van_tu_khai_chon_dai_bai_kiem_tra(placement_client: TestClient) -> None:
    assert placement_client.patch("/api/me", json={"claimed_rating": 2250}).status_code == 200

    ids = placement_ids(practice(placement_client))

    assert ids == [p["puzzle_id"] for p in SETS["2200"]]
    assert placement_client.get("/api/me").json()["claimed_rating"] == 2250


def test_rating_van_tu_khai_ngoai_khoang_bi_tu_choi(placement_client: TestClient) -> None:
    for rating in (100, 4000):
        assert placement_client.patch("/api/me", json={"claimed_rating": rating}).status_code == 422


def test_rating_van_tu_khai_lam_tien_nghiem_nang_luc(placement_client: TestClient) -> None:
    placement_client.patch("/api/me", json={"claimed_rating": 2250})

    assert placement_client.get("/api/profile").json()["theta"] == 2250


def test_lan_giai_trong_bai_kiem_tra_duoc_danh_dau_va_cap_nhat_nang_luc(placement_client: TestClient) -> None:
    first = SETS["1400"][0]["puzzle_id"]

    finish_wrong(placement_client, first)

    history = placement_client.get("/api/attempts").json()
    assert [(a["puzzle_id"], a["placement"]) for a in history] == [(first, True)]
    profile = placement_client.get("/api/profile").json()
    assert profile["attempts"] == 1
    assert profile["theta"] < 1500
    assert practice(placement_client)["placement"]["completed"] == 1


def test_bo_do_roi_quay_lai_thi_lam_tiep_bai_tap_dang_do(placement_client: TestClient) -> None:
    second = SETS["1400"][1]["puzzle_id"]
    finish_wrong(placement_client, SETS["1400"][0]["puzzle_id"])
    start(placement_client, second)  # mở rồi bỏ dở

    assert placement_client.get("/api/puzzles/next").json()["puzzle_id"] == second


def test_dai_chot_khi_bat_dau_lam_bai_kiem_tra(placement_client: TestClient) -> None:
    start(placement_client, SETS["1400"][0]["puzzle_id"])
    body = practice(placement_client)
    assert body["placement"]["started"] is True

    placement_client.patch("/api/me", json={"claimed_rating": 2250})

    assert placement_ids(practice(placement_client)) == [p["puzzle_id"] for p in SETS["1400"]]


def test_xong_bai_kiem_tra_thi_nhan_buoi_luyen(placement_client: TestClient) -> None:
    for p in SETS["1400"]:
        finish_wrong(placement_client, p["puzzle_id"])

    body = practice(placement_client)

    assert body["mode"] == "practice"
    assert body["placement"] is None
    assert len(body["items"]) >= 3
    assert not {p["puzzle_id"] for p in SETS["1400"]} & set(placement_ids(body))
    assert placement_client.get("/api/puzzles/next").json()["puzzle_id"] == body["items"][0]["puzzle_id"]


def test_nguoi_choi_da_co_lan_giai_truoc_do_khong_phai_lam_bai_kiem_tra(placement_client: TestClient) -> None:
    outside = next(pid for pid in RATINGS if pid not in {p["puzzle_id"] for s in SETS.values() for p in s})
    start(placement_client, outside)  # đã có lần giải trước khi bài kiểm tra bắt đầu

    assert practice(placement_client)["mode"] == "practice"


def test_khong_sua_duoc_rating_van_sau_khi_da_bat_dau(placement_client: TestClient) -> None:
    finish_wrong(placement_client, SETS["1400"][0]["puzzle_id"])
    theta = placement_client.get("/api/profile").json()["theta"]

    r = placement_client.patch("/api/me", json={"claimed_rating": 2250})

    assert r.status_code == 409
    assert placement_client.get("/api/profile").json()["theta"] == theta


def test_mo_bai_tap_cua_dai_khac_van_giu_bai_kiem_tra(placement_client: TestClient) -> None:
    # Danh sách cũ (dải 1400) còn trên màn hình, người chơi đổi rating rồi mới mở bài tập đầu tiên.
    first = placement_ids(practice(placement_client))[0]
    placement_client.patch("/api/me", json={"claimed_rating": 2250})

    start(placement_client, first)

    body = practice(placement_client)
    assert body["mode"] == "placement"
    assert placement_ids(body) == [p["puzzle_id"] for p in SETS["1400"]]
    assert placement_client.get("/api/attempts").json()[0]["placement"] is True


def test_bo_bai_kiem_tra_co_bai_tap_khong_co_trong_kho_van_lam_duoc(tmp_path: Path) -> None:
    broken = json.loads(PLACEMENT_SAMPLE.read_text(encoding="utf-8"))
    broken["sets"]["1400"].insert(0, {"skill": "fork", "puzzle_id": "KHONG_CO"})
    path = tmp_path / "placement.json"
    path.write_text(json.dumps(broken), encoding="utf-8")
    app = create_app(database_url="sqlite:///:memory:", puzzle_catalog=PUZZLE_SAMPLE, placement_sets=path)
    with TestClient(app) as client:
        register_new_player(client, "a@example.com")
        body = practice(client)
        assert "KHONG_CO" not in placement_ids(body)
        assert body["placement"]["total"] == len(SETS["1400"])
        next_id = client.get("/api/puzzles/next").json()["puzzle_id"]
        assert client.post("/api/attempts", json={"puzzle_id": next_id}).status_code == 201
