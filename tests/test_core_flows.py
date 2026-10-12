import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database
import main


def setup_function():
    # Tests each use a fresh SQLite database configured by the fixture below.
    pass


def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_NAME", str(tmp_path / "retention-test.db"))
    database.init_db()


def create_business(owner_id=None, offer="Opening offer"):
    conn = database.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO businesses
               (name, category, latitude, longitude, address, offer, owner_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("Test Cafe", "cafe", 23.2, 77.4, "1 Test Road", offer, owner_id),
        )
        business_id = cur.lastrowid
        conn.commit()
        return business_id
    finally:
        conn.close()


def signup_customer(client, email="customer@example.com"):
    response = client.post(
        "/api/signup",
        data={"name": "Test Customer", "email": email, "password": "correct-horse-123"},
    )
    assert response.status_code == 200, response.text
    return response


def signup_owner(client, email="owner@example.com"):
    response = client.post(
        "/api/owner/signup",
        data={"name": "Test Owner", "email": email, "password": "correct-horse-123"},
    )
    assert response.status_code == 200, response.text
    return response


def test_customer_signup_login_follow_and_read_offer(tmp_path, monkeypatch):
    isolated_database(tmp_path, monkeypatch)
    business_id = create_business()
    client = TestClient(main.app)

    signup_customer(client)
    login = client.post(
        "/api/login",
        data={"email": "customer@example.com", "password": "correct-horse-123"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["user"]["role"] == "customer"
    assert client.get("/api/me").json()["logged_in"] is True

    follow = client.post(f"/api/businesses/{business_id}/follow")
    assert follow.status_code == 200, follow.text
    assert follow.json()["following"] is True
    assert client.get(f"/api/businesses/{business_id}/follow").json()["following"] is True

    following = client.get("/api/following")
    assert following.status_code == 200
    assert [item["id"] for item in following.json()] == [business_id]
    detail = client.get(f"/api/businesses/{business_id}")
    assert detail.status_code == 200
    assert detail.json()["offer"] == "Opening offer"


def test_owner_can_update_and_clear_offer_but_customer_cannot(tmp_path, monkeypatch):
    isolated_database(tmp_path, monkeypatch)
    owner_client = TestClient(main.app)
    signup_owner(owner_client)
    login = owner_client.post(
        "/api/owner/login",
        data={"email": "owner@example.com", "password": "correct-horse-123"},
    )
    assert login.status_code == 200, login.text
    owner_id = login.json()["user"]["id"]
    business_id = create_business(owner_id=owner_id)

    updated = owner_client.post(
        f"/api/businesses/{business_id}/offer",
        data={"offer": "10% off today"},
    )
    assert updated.status_code == 200, updated.text
    assert database.get_business_by_id(business_id)[6] == "10% off today"

    cleared = owner_client.post(
        f"/api/businesses/{business_id}/offer",
        data={"offer": ""},
    )
    assert cleared.status_code == 200, cleared.text
    assert database.get_business_by_id(business_id)[6] == ""

    customer_client = TestClient(main.app)
    signup_customer(customer_client)
    customer_client.post(
        "/api/login",
        data={"email": "customer@example.com", "password": "correct-horse-123"},
    )
    forbidden = customer_client.post(
        f"/api/businesses/{business_id}/offer",
        data={"offer": "unauthorized"},
    )
    assert forbidden.status_code == 403


def test_owner_claim_stays_pending_until_admin_approval(tmp_path, monkeypatch):
    isolated_database(tmp_path, monkeypatch)
    monkeypatch.setenv("BUSINESS_MIGRATION_SECRET", "test-only-secret")
    owner_client = TestClient(main.app)
    signup_owner(owner_client)
    owner_client.post(
        "/api/owner/login",
        data={"email": "owner@example.com", "password": "correct-horse-123"},
    )
    business_id = create_business(owner_id=None, offer="")

    claim = owner_client.post(
        "/api/owner/business-claims",
        data={"business_id": str(business_id), "note": "Verify official business site"},
    )
    assert claim.status_code == 200, claim.text
    assert claim.json()["status"] == "pending"
    assert database.get_business_by_id(business_id)[7] is None

    denied = TestClient(main.app).get("/api/admin/business-claims")
    assert denied.status_code == 404

    admin = TestClient(main.app)
    pending = admin.get(
        "/api/admin/business-claims",
        headers={"X-Migration-Secret": "test-only-secret"},
    )
    assert pending.status_code == 200, pending.text
    assert pending.json()[0]["business_id"] == business_id

    review = admin.post(
        f"/api/admin/business-claims/{claim.json()['claim_id']}/review",
        headers={"X-Migration-Secret": "test-only-secret"},
        json={"status": "approved"},
    )
    assert review.status_code == 200, review.text
    assert database.get_business_by_id(business_id)[7] == owner_client.get("/api/me").json()["user"]["id"]


def test_invalid_origin_cannot_submit_state_change(tmp_path, monkeypatch):
    isolated_database(tmp_path, monkeypatch)
    client = TestClient(main.app)
    signup_customer(client)
    response = client.post(
        "/api/login",
        data={"email": "customer@example.com", "password": "correct-horse-123"},
        headers={"Origin": "https://attacker.invalid"},
    )
    assert response.status_code == 403
