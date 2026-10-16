import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database
import main


@pytest.fixture
def profile_client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_NAME", str(tmp_path / "profiles.db"))
    monkeypatch.setattr(database, "USE_POSTGRES", False)
    monkeypatch.setattr(main, "IS_PRODUCTION", False)
    monkeypatch.setattr(main, "_rate_limit_buckets", {})
    database.init_db()

    conn = database.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            ("Owner", "owner@example.com", "hash", "owner"),
        )
        owner_id = cur.lastrowid
        cur.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            ("Customer", "customer@example.com", "hash", "customer"),
        )
        customer_id = cur.lastrowid
        cur.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            ("Other Customer", "other@example.com", "hash", "customer"),
        )
        other_customer_id = cur.lastrowid
        cur.execute(
            "INSERT INTO businesses (name, category, address, owner_id) VALUES (?, ?, ?, ?)",
            ("Owner Cafe", "cafe", "1 Main Road", owner_id),
        )
        business_id = cur.lastrowid
        cur.execute(
            "INSERT INTO businesses (name, category, address, owner_id) VALUES (?, ?, ?, NULL)",
            ("Unclaimed Cafe", "cafe", "2 Main Road"),
        )
        unclaimed_id = cur.lastrowid
        cur.execute("INSERT INTO follows (user_id, business_id) VALUES (?, ?)", (customer_id, business_id))
        conn.commit()
    finally:
        conn.close()

    tokens = {
        "owner": main.create_secure_session(owner_id),
        "customer": main.create_secure_session(customer_id),
    }
    with TestClient(main.app) as client:
        yield {
            "client": client, "tokens": tokens, "business_id": business_id,
            "unclaimed_id": unclaimed_id, "customer_id": customer_id,
            "other_customer_id": other_customer_id,
        }


def use_session(client, token):
    client.cookies.clear()
    client.cookies.set(main.SESSION_COOKIE_NAME, token)


def test_customer_can_update_profile_but_not_take_another_email(profile_client):
    client = profile_client["client"]
    use_session(client, profile_client["tokens"]["customer"])
    response = client.post(
        "/api/me/profile",
        data={"name": "Updated Customer", "email": "updated@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["user"]["name"] == "Updated Customer"
    assert client.get("/api/me").json()["user"]["email"] == "updated@example.com"

    duplicate = client.post(
        "/api/me/profile",
        data={"name": "Updated Customer", "email": "owner@example.com"},
    )
    assert duplicate.status_code == 409

    invalid = client.post(
        "/api/me/profile",
        data={"name": "Updated Customer", "email": "not-an-email"},
    )
    assert invalid.status_code == 400


def test_owner_customer_list_is_scoped_to_their_business(profile_client):
    client = profile_client["client"]
    assert client.get(f"/api/owner/businesses/{profile_client['business_id']}/customers").status_code == 401
    use_session(client, profile_client["tokens"]["customer"])
    assert client.get(f"/api/owner/businesses/{profile_client['business_id']}/customers").status_code == 403

    use_session(client, profile_client["tokens"]["owner"])
    response = client.get(f"/api/owner/businesses/{profile_client['business_id']}/customers")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["email"] == "customer@example.com"
    assert client.get(f"/api/owner/businesses/{profile_client['unclaimed_id']}/customers").status_code == 403
