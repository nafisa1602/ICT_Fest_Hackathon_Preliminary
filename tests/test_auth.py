import pytest
import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.main import app
from app.auth import create_access_token, decode_token
from app.models import User

client = TestClient(app)

def test_access_token_expiration_lifetime():
    # Create a mock user
    user = User(id=999, org_id="test-org", role="user")
    token = create_access_token(user)
    payload = decode_token(token)
    
    # Expiration should be exactly 15 minutes (900 seconds) after issued-at time
    assert payload["exp"] - payload["iat"] == 15 * 60

def test_logout_revocation_flow():
    # Register and login a user with unique organization
    org = f"org-{uuid.uuid4().hex}"
    reg = client.post(
        "/auth/register",
        json={"org_name": org, "username": "bob", "password": "password123"},
    )
    assert reg.status_code == 201

    login = client.post(
        "/auth/login",
        json={"org_name": org, "username": "bob", "password": "password123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify authorization works
    res = client.get("/bookings", headers=headers)
    assert res.status_code == 200

    # Logout to revoke the token
    logout_res = client.post("/auth/logout", headers=headers)
    assert logout_res.status_code == 200
    assert logout_res.json() == {"status": "ok"}

    # Attempt to request again with the revoked token; should fail with 401 UNAUTHORIZED
    res_after_logout = client.get("/bookings", headers=headers)
    assert res_after_logout.status_code == 401
    assert res_after_logout.json()["detail"] == "Token has been revoked"

def test_refresh_token_single_use():
    org = f"org-{uuid.uuid4().hex}"
    reg = client.post(
        "/auth/register",
        json={"org_name": org, "username": "charlie", "password": "password123"},
    )
    assert reg.status_code == 201

    login = client.post(
        "/auth/login",
        json={"org_name": org, "username": "charlie", "password": "password123"},
    )
    assert login.status_code == 200
    refresh_token = login.json()["refresh_token"]

    # Use the refresh token once
    refresh_res = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_res.status_code == 200

    # Attempt to use the same refresh token a second time; should fail
    second_refresh_res = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert second_refresh_res.status_code == 401
    assert second_refresh_res.json()["detail"] == "Token has been revoked"

def test_duplicate_username_registration():
    org = f"org-{uuid.uuid4().hex}"
    reg1 = client.post(
        "/auth/register",
        json={"org_name": org, "username": "danny", "password": "password123"},
    )
    assert reg1.status_code == 201

    reg2 = client.post(
        "/auth/register",
        json={"org_name": org, "username": "danny", "password": "password456"},
    )
    assert reg2.status_code == 409
    assert reg2.json()["code"] == "USERNAME_TAKEN"
