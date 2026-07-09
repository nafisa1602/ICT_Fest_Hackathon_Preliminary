import pytest
import uuid
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def _register_and_login(username: str, org: str):
    reg = client.post(
        "/auth/register",
        json={"org_name": org, "username": username, "password": "password123"},
    )
    assert reg.status_code == 201
    login = client.post(
        "/auth/login",
        json={"org_name": org, "username": username, "password": "password123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_booking_start_time_in_past_rejected():
    org = f"org-{uuid.uuid4().hex}"
    admin_headers = _register_and_login("admin1", org)

    # Create a room
    room = client.post(
        "/rooms",
        json={"name": "Room A", "capacity": 5, "hourly_rate_cents": 1000},
        headers=admin_headers,
    )
    assert room.status_code == 201
    room_id = room.json()["id"]

    # Attempt to book in the past (e.g. 2 minutes ago)
    past_time = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    future_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    res = client.post(
        "/bookings",
        json={"room_id": room_id, "start_time": past_time, "end_time": future_time},
        headers=admin_headers,
    )
    assert res.status_code == 400
    assert res.json()["code"] == "INVALID_BOOKING_WINDOW"

def test_booking_end_time_before_or_equal_start_time_rejected():
    org = f"org-{uuid.uuid4().hex}"
    admin_headers = _register_and_login("admin1", org)

    room = client.post(
        "/rooms",
        json={"name": "Room A", "capacity": 5, "hourly_rate_cents": 1000},
        headers=admin_headers,
    )
    room_id = room.json()["id"]

    start = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    end_before = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    end_equal = start

    # end_time < start_time
    res1 = client.post(
        "/bookings",
        json={"room_id": room_id, "start_time": start, "end_time": end_before},
        headers=admin_headers,
    )
    assert res1.status_code == 400
    assert res1.json()["code"] == "INVALID_BOOKING_WINDOW"

    # end_time == start_time
    res2 = client.post(
        "/bookings",
        json={"room_id": room_id, "start_time": start, "end_time": end_equal},
        headers=admin_headers,
    )
    assert res2.status_code == 400
    assert res2.json()["code"] == "INVALID_BOOKING_WINDOW"

def test_back_to_back_bookings_allowed():
    org = f"org-{uuid.uuid4().hex}"
    admin_headers = _register_and_login("admin1", org)

    room = client.post(
        "/rooms",
        json={"name": "Room A", "capacity": 5, "hourly_rate_cents": 1000},
        headers=admin_headers,
    )
    room_id = room.json()["id"]

    t0 = (datetime.now(timezone.utc) + timedelta(hours=10)).replace(minute=0, second=0, microsecond=0)
    t1 = t0 + timedelta(hours=1)
    t2 = t0 + timedelta(hours=2)

    # First booking [t0, t1]
    res1 = client.post(
        "/bookings",
        json={"room_id": room_id, "start_time": t0.isoformat(), "end_time": t1.isoformat()},
        headers=admin_headers,
    )
    assert res1.status_code == 201

    # Back-to-back booking [t1, t2] (starts exactly when first ends)
    res2 = client.post(
        "/bookings",
        json={"room_id": room_id, "start_time": t1.isoformat(), "end_time": t2.isoformat()},
        headers=admin_headers,
    )
    assert res2.status_code == 201

def test_booking_pagination_and_sorting():
    org = f"org-{uuid.uuid4().hex}"
    admin_headers = _register_and_login("admin1", org)

    room = client.post(
        "/rooms",
        json={"name": "Room A", "capacity": 5, "hourly_rate_cents": 1000},
        headers=admin_headers,
    )
    room_id = room.json()["id"]

    # Create 3 bookings in chronological order: t + 10h, t + 20h, t + 15h
    base_time = (datetime.now(timezone.utc) + timedelta(hours=5)).replace(minute=0, second=0, microsecond=0)
    
    t_10 = (base_time + timedelta(hours=10)).isoformat()
    t_11 = (base_time + timedelta(hours=11)).isoformat()
    t_15 = (base_time + timedelta(hours=15)).isoformat()
    t_16 = (base_time + timedelta(hours=16)).isoformat()
    t_20 = (base_time + timedelta(hours=20)).isoformat()
    t_21 = (base_time + timedelta(hours=21)).isoformat()

    client.post("/bookings", json={"room_id": room_id, "start_time": t_10, "end_time": t_11}, headers=admin_headers)
    client.post("/bookings", json={"room_id": room_id, "start_time": t_20, "end_time": t_21}, headers=admin_headers)
    client.post("/bookings", json={"room_id": room_id, "start_time": t_15, "end_time": t_16}, headers=admin_headers)

    # Get bookings with limit=2, page=1
    res = client.get("/bookings?limit=2&page=1", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) == 2
    assert data["total"] == 3
    # Check that sorting is ascending by start_time: t_10, then t_15
    assert data["items"][0]["start_time"].startswith(t_10[:19])
    assert data["items"][1]["start_time"].startswith(t_15[:19])

    # Get bookings with limit=2, page=2
    res2 = client.get("/bookings?limit=2&page=2", headers=admin_headers)
    assert res2.status_code == 200
    data2 = res2.json()
    assert len(data2["items"]) == 1
    assert data2["items"][0]["start_time"].startswith(t_20[:19])

def test_booking_visibility_non_admin_leak():
    org = f"org-{uuid.uuid4().hex}"
    admin_headers = _register_and_login("admin1", org)
    member_headers = _register_and_login("member1", org)

    room = client.post(
        "/rooms",
        json={"name": "Room A", "capacity": 5, "hourly_rate_cents": 1000},
        headers=admin_headers,
    )
    room_id = room.json()["id"]

    # Admin makes a booking
    t0 = (datetime.now(timezone.utc) + timedelta(hours=10)).replace(minute=0, second=0, microsecond=0)
    t1 = t0 + timedelta(hours=1)
    booking_res = client.post(
        "/bookings",
        json={"room_id": room_id, "start_time": t0.isoformat(), "end_time": t1.isoformat()},
        headers=admin_headers,
    )
    booking_id = booking_res.json()["id"]

    # Non-admin member attempts to view admin's booking detail
    view_res = client.get(f"/bookings/{booking_id}", headers=member_headers)
    assert view_res.status_code == 404
    assert view_res.json()["code"] == "BOOKING_NOT_FOUND"

    # Admin can view it successfully
    view_admin_res = client.get(f"/bookings/{booking_id}", headers=admin_headers)
    assert view_admin_res.status_code == 200

def test_refund_notice_tiers_and_rounding():
    org = f"org-{uuid.uuid4().hex}"
    admin_headers = _register_and_login("admin1", org)

    room = client.post(
        "/rooms",
        json={"name": "Room A", "capacity": 5, "hourly_rate_cents": 1001}, # Hourly rate has odd cents
        headers=admin_headers,
    )
    room_id = room.json()["id"]

    # 1. >= 48 hours notice -> should be 100% refund (using 48h + 10s buffer)
    t_48 = datetime.now(timezone.utc) + timedelta(hours=48, seconds=10)
    b_48_res = client.post(
        "/bookings",
        json={"room_id": room_id, "start_time": t_48.isoformat(), "end_time": (t_48 + timedelta(hours=1)).isoformat()},
        headers=admin_headers,
    )
    assert b_48_res.status_code == 201
    b_48_id = b_48_res.json()["id"]
    cancel_48 = client.post(f"/bookings/{b_48_id}/cancel", headers=admin_headers)
    assert cancel_48.status_code == 200
    assert cancel_48.json()["refund_percent"] == 100
    assert cancel_48.json()["refund_amount_cents"] == 1001

    # 2. >= 24 hours notice -> 50% refund, with proper rounding (using 24h + 10s buffer)
    # 50% of 1001 is 500.5 cents -> Python's round() uses round-to-even: round(500.5) is 500.
    t_24 = datetime.now(timezone.utc) + timedelta(hours=24, seconds=10)
    b_24_res = client.post(
        "/bookings",
        json={"room_id": room_id, "start_time": t_24.isoformat(), "end_time": (t_24 + timedelta(hours=1)).isoformat()},
        headers=admin_headers,
    )
    b_24_id = b_24_res.json()["id"]
    cancel_24 = client.post(f"/bookings/{b_24_id}/cancel", headers=admin_headers)
    assert cancel_24.status_code == 200
    assert cancel_24.json()["refund_percent"] == 50
    assert cancel_24.json()["refund_amount_cents"] == 500

    # 3. Less than 24 hours notice -> 0% refund (using 23h 59m)
    t_12 = datetime.now(timezone.utc) + timedelta(hours=23, minutes=59)
    b_12_res = client.post(
        "/bookings",
        json={"room_id": room_id, "start_time": t_12.isoformat(), "end_time": (t_12 + timedelta(hours=1)).isoformat()},
        headers=admin_headers,
    )
    b_12_id = b_12_res.json()["id"]
    cancel_12 = client.post(f"/bookings/{b_12_id}/cancel", headers=admin_headers)
    assert cancel_12.status_code == 200
    assert cancel_12.json()["refund_percent"] == 0
    assert cancel_12.json()["refund_amount_cents"] == 0

def test_cache_invalidation_availability_on_cancel():
    org = f"org-{uuid.uuid4().hex}"
    admin_headers = _register_and_login("admin1", org)

    room = client.post(
        "/rooms",
        json={"name": "Room A", "capacity": 5, "hourly_rate_cents": 1000},
        headers=admin_headers,
    )
    room_id = room.json()["id"]

    t0 = datetime.now(timezone.utc) + timedelta(hours=10)
    date_str = t0.date().isoformat()

    # Query availability (initially empty)
    res_init = client.get(f"/rooms/{room_id}/availability?date={date_str}", headers=admin_headers)
    assert res_init.status_code == 200
    assert len(res_init.json()["busy"]) == 0

    # Book room
    booking_res = client.post(
        "/bookings",
        json={"room_id": room_id, "start_time": t0.isoformat(), "end_time": (t0 + timedelta(hours=1)).isoformat()},
        headers=admin_headers,
    )
    booking_id = booking_res.json()["id"]

    # Query availability (should be 1 busy interval, caching it)
    res_booked = client.get(f"/rooms/{room_id}/availability?date={date_str}", headers=admin_headers)
    assert res_booked.status_code == 200
    assert len(res_booked.json()["busy"]) == 1

    # Cancel booking (must invalidate availability cache)
    cancel_res = client.post(f"/bookings/{booking_id}/cancel", headers=admin_headers)
    assert cancel_res.status_code == 200

    # Query availability again (should be empty if cache was invalidated, otherwise would still have cached busy interval)
    res_final = client.get(f"/rooms/{room_id}/availability?date={date_str}", headers=admin_headers)
    assert res_final.status_code == 200
    assert len(res_final.json()["busy"]) == 0

def test_cache_invalidation_report_on_create():
    org = f"org-{uuid.uuid4().hex}"
    admin_headers = _register_and_login("admin1", org)

    room = client.post(
        "/rooms",
        json={"name": "Room A", "capacity": 5, "hourly_rate_cents": 1000},
        headers=admin_headers,
    )
    room_id = room.json()["id"]

    t0 = datetime.now(timezone.utc) + timedelta(hours=10)
    date_str = t0.date().isoformat()

    # Query usage report first to cache it
    report_init = client.get(f"/admin/usage-report?from={date_str}&to={date_str}", headers=admin_headers)
    assert report_init.status_code == 200
    assert report_init.json()["rooms"][0]["confirmed_bookings"] == 0

    # Create a booking (must invalidate the report cache)
    booking_res = client.post(
        "/bookings",
        json={"room_id": room_id, "start_time": t0.isoformat(), "end_time": (t0 + timedelta(hours=1)).isoformat()},
        headers=admin_headers,
    )
    assert booking_res.status_code == 201

    # Query usage report again (should show 1 confirmed booking if cache was invalidated)
    report_final = client.get(f"/admin/usage-report?from={date_str}&to={date_str}", headers=admin_headers)
    assert report_final.status_code == 200
    assert report_final.json()["rooms"][0]["confirmed_bookings"] == 1

def test_admin_export_cross_org_bypass():
    org_a = f"org-{uuid.uuid4().hex}"
    admin_a_headers = _register_and_login("admin_a", org_a)

    org_b = f"org-{uuid.uuid4().hex}"
    admin_b_headers = _register_and_login("admin_b", org_b)

    # Org B creates a room
    room_b = client.post(
        "/rooms",
        json={"name": "Org B Room", "capacity": 5, "hourly_rate_cents": 1000},
        headers=admin_b_headers,
    )
    assert room_b.status_code == 201
    room_b_id = room_b.json()["id"]

    # Admin A attempts to export bookings of Room B (Org B's room)
    export_res = client.get(f"/admin/export?include_all=true&room_id={room_b_id}", headers=admin_a_headers)
    assert export_res.status_code == 404
    assert export_res.json()["code"] == "ROOM_NOT_FOUND"
