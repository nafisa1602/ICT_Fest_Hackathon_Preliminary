"""Happy-path smoke test covering the core booking flow.

Run with ``pytest`` after installing requirements. It exercises a single,
sequential golden path and is not a substitute for full API testing.
"""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _future(hours: int) -> str:
    dt = (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(
        minute=0, second=0, microsecond=0
    )
    # Ensure the API sees an explicit UTC designator ("Z"), matching the
    # format the endpoints emit in their own responses.
    return dt.isoformat().replace("+00:00", "Z")


def test_core_flow():
    assert client.get("/health").json() == {"status": "ok"}

    org = f"acme-{datetime.now().timestamp()}"
    reg = client.post(
        "/auth/register",
        json={"org_name": org, "username": "alice", "password": "pw12345"},
    )
    assert reg.status_code == 201
    assert reg.json()["role"] == "admin"

    login = client.post(
        "/auth/login",
        json={"org_name": org, "username": "alice", "password": "pw12345"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    room = client.post(
        "/rooms",
        json={"name": "Focus Room", "capacity": 4, "hourly_rate_cents": 1000},
        headers=headers,
    )
    assert room.status_code == 201
    room_id = room.json()["id"]

    booking = client.post(
        "/bookings",
        json={"room_id": room_id, "start_time": _future(50), "end_time": _future(52)},
        headers=headers,
    )
    assert booking.status_code == 201
    booking_data = booking.json()

    # Validate full response structure, not just price.
    for field in ("id", "reference_code", "start_time", "end_time", "status", "created_at"):
        assert field in booking_data, f"missing field: {field}"

    assert booking_data["price_cents"] == 2000
    assert booking_data["status"] == "confirmed"

    reference_code = booking_data["reference_code"]
    assert reference_code is not None
    assert reference_code.startswith("CW-")

    booking_id = booking_data["id"]
    booking_start = booking_data["start_time"]

    # Test retrieving single booking details
    get_res = client.get(f"/bookings/{booking_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["start_time"] == booking_start
    assert get_res.json()["reference_code"] == reference_code

    # Default listing
    listing = client.get("/bookings", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["total"] >= 1

    # Explicit pagination params, to catch offset/limit bugs
    listing_p1 = client.get("/bookings?page=1&limit=5", headers=headers)
    assert listing_p1.status_code == 200
    listing_p1_data = listing_p1.json()
    assert listing_p1_data["limit"] == 5
    assert listing_p1_data["page"] == 1
    assert len(listing_p1_data["items"]) <= 5

    # Cancellation / refund flow
    cancel = client.post(f"/bookings/{booking_id}/cancel", headers=headers)
    assert cancel.status_code == 200
    cancel_data = cancel.json()
    assert cancel_data["status"] == "cancelled"
    assert "refund_amount_cents" in cancel_data
    assert 0 <= cancel_data["refund_amount_cents"] <= booking_data["price_cents"]
