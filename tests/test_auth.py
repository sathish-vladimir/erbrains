def test_register_and_login(client):
    reg = client.post(
        "/auth/register",
        json={"email": "a@example.com", "password": "secret123", "full_name": "A"},
    )
    assert reg.status_code == 201
    assert reg.json()["email"] == "a@example.com"

    login = client.post(
        "/auth/login", json={"email": "a@example.com", "password": "secret123"}
    )
    assert login.status_code == 200
    assert "access_token" in login.json()


def test_duplicate_email_registration_rejected(client):
    payload = {"email": "dup@example.com", "password": "secret123"}
    first = client.post("/auth/register", json=payload)
    second = client.post("/auth/register", json=payload)
    assert first.status_code == 201
    assert second.status_code == 409


def test_login_with_wrong_password_rejected(client):
    client.post("/auth/register", json={"email": "b@example.com", "password": "correct-pass"})
    resp = client.post("/auth/login", json={"email": "b@example.com", "password": "wrong-pass"})
    assert resp.status_code == 401


def test_protected_endpoint_requires_token(client):
    resp = client.get("/devices")
    assert resp.status_code == 401
