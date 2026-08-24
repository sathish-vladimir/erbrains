"""Covers the health-reading ingestion/dedup logic - this is the part of the
app where a bug could cause data loss (missed readings) or duplicated data
(the offline sync retrying and double-counting steps/heart rate)."""


def _register_device(client, headers, device_id="FITRING-001"):
    resp = client.post("/devices", json={"device_id": device_id}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


def test_create_reading(client, auth_headers):
    device_id = _register_device(client, auth_headers)
    resp = client.post(
        "/health/readings",
        json={
            "client_reading_id": "r-1",
            "device_id": device_id,
            "heart_rate": 78,
            "spo2": 98,
            "steps": 6420,
            "battery": 72,
            "recorded_at": "2026-08-17T10:30:00Z",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["heart_rate"] == 78


def test_duplicate_reading_is_rejected(client, auth_headers):
    """Same client_reading_id sent twice for the same device must not create
    two rows - this is what protects step/heart-rate totals from inflating
    if the mobile app retries a sync after a flaky connection."""
    device_id = _register_device(client, auth_headers)
    payload = {
        "client_reading_id": "r-1",
        "device_id": device_id,
        "heart_rate": 78,
        "spo2": 98,
        "steps": 6420,
        "recorded_at": "2026-08-17T10:30:00Z",
    }
    first = client.post("/health/readings", json=payload, headers=auth_headers)
    second = client.post("/health/readings", json=payload, headers=auth_headers)

    assert first.status_code == 201
    assert second.status_code == 409

    listing = client.get("/health/readings", headers=auth_headers)
    assert len(listing.json()) == 1


def test_batch_sync_deduplicates_and_is_idempotent(client, auth_headers):
    """Simulates the assignment's target scenario: 100 readings generated
    offline, synced once connectivity returns, then re-sent (as would
    happen if the client retried the whole batch after a timeout)."""
    device_id = _register_device(client, auth_headers)
    readings = [
        {
            "client_reading_id": f"batch-{i}",
            "device_id": device_id,
            "heart_rate": 70 + (i % 20),
            "spo2": 97,
            "steps": 100 * i,
            "recorded_at": "2026-08-17T11:00:00Z",
        }
        for i in range(100)
    ]

    first = client.post("/health/readings/batch", json={"readings": readings}, headers=auth_headers)
    assert first.status_code == 201
    body = first.json()
    assert len(body["created"]) == 100
    assert body["duplicates_skipped"] == 0

    # Retry the exact same batch - none of it should be re-inserted.
    second = client.post("/health/readings/batch", json={"readings": readings}, headers=auth_headers)
    body2 = second.json()
    assert len(body2["created"]) == 0
    assert body2["duplicates_skipped"] == 100

    listing = client.get("/health/readings", headers=auth_headers, params={"limit": 500})
    assert len(listing.json()) == 100


def test_reading_requires_auth(client):
    resp = client.post(
        "/health/readings",
        json={
            "client_reading_id": "r-1",
            "device_id": 1,
            "recorded_at": "2026-08-17T10:30:00Z",
        },
    )
    assert resp.status_code == 401


def test_cannot_post_reading_for_device_owned_by_another_user(client, auth_headers):
    device_id = _register_device(client, auth_headers)

    client.post(
        "/auth/register",
        json={"email": "other@example.com", "password": "secret123"},
    )
    other_login = client.post("/auth/login", json={"email": "other@example.com", "password": "secret123"})
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    resp = client.post(
        "/health/readings",
        json={
            "client_reading_id": "r-1",
            "device_id": device_id,
            "recorded_at": "2026-08-17T10:30:00Z",
        },
        headers=other_headers,
    )
    assert resp.status_code == 404
