from fastapi.testclient import TestClient

EMAIL = "an@example.com"
PASSWORD = "matkhau-dai-du"


def register(client: TestClient, email: str = EMAIL, password: str = PASSWORD) -> None:
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "display_name": "An"},
    )
    assert r.status_code == 201, r.text


def test_dang_ky_xong_thi_da_dang_nhap_va_thay_ten_minh(client: TestClient) -> None:
    register(client)

    r = client.get("/api/me")

    assert r.status_code == 200
    assert r.json() == {"email": EMAIL, "display_name": "An", "daily_minutes": 30}


def test_email_da_dang_ky_bi_tu_choi_ke_ca_khac_chu_hoa(client: TestClient) -> None:
    register(client)

    r = client.post(
        "/api/auth/register",
        json={"email": "An@Example.com", "password": PASSWORD, "display_name": "An 2"},
    )

    assert r.status_code == 409
    assert r.json()["detail"] == "Email này đã được đăng ký"


def test_mat_khau_qua_ngan_hoac_qua_dai_bi_tu_choi(client: TestClient) -> None:
    for password in ("ngan", "a" * 73, "ệ" * 30):  # "ệ" là 3 byte UTF-8: 90 byte
        r = client.post(
            "/api/auth/register",
            json={"email": EMAIL, "password": password, "display_name": "An"},
        )
        assert r.status_code == 422, password

    assert client.get("/api/me").status_code == 401


def test_chua_dang_nhap_thi_khong_doc_duoc_nguoi_choi(client: TestClient) -> None:
    r = client.get("/api/me")

    assert r.status_code == 401


def test_dang_nhap_dung_mat_khau_thi_vao_duoc(client: TestClient) -> None:
    register(client)
    client.cookies.clear()

    r = client.post("/api/auth/login", json={"email": "AN@example.com", "password": PASSWORD})

    assert r.status_code == 200
    assert client.get("/api/me").json()["display_name"] == "An"


def test_sai_mat_khau_hoac_email_la_thi_bi_bao_loi_va_khong_vao_duoc(client: TestClient) -> None:
    register(client)
    client.cookies.clear()

    sai_mat_khau = client.post("/api/auth/login", json={"email": EMAIL, "password": "sai-roi-123"})
    email_la = client.post("/api/auth/login", json={"email": "la@example.com", "password": PASSWORD})

    for r in (sai_mat_khau, email_la):
        assert r.status_code == 401
        assert r.json()["detail"] == "Email hoặc mật khẩu không đúng"
    assert client.get("/api/me").status_code == 401


def test_dang_xuat_huy_phien_ke_ca_khi_gui_lai_cookie_cu(client: TestClient) -> None:
    register(client)
    cookie_cu = dict(client.cookies)

    r = client.post("/api/auth/logout")

    assert r.status_code == 204
    assert client.get("/api/me").status_code == 401
    client.cookies.update(cookie_cu)
    assert client.get("/api/me").status_code == 401
