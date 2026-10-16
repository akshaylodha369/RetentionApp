import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database
import main


@pytest.fixture
def notification_client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_NAME", str(tmp_path / "notifications.db"))
    monkeypatch.setattr(database, "USE_POSTGRES", False)
    monkeypatch.setattr(main, "IS_PRODUCTION", False)
    monkeypatch.setattr(main, "_rate_limit_buckets", {})
    database.init_db()

    def add_user(name, email, role):
        conn = database.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
                (name, email, "test-hash", role),
            )
            user_id = cur.lastrowid
            conn.commit()
            return user_id
        finally:
            conn.close()

    owner = add_user("Owner", "owner@example.com", "owner")
    customer_a = add_user("Customer A", "a@example.com", "customer")
    customer_b = add_user("Customer B", "b@example.com", "customer")
    conn = database.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO businesses (name, category, address, owner_id) VALUES (?, ?, ?, ?)",
            ("Test Cafe", "cafe", "1 Main Road", owner),
        )
        business_id = cur.lastrowid
        cur.execute("INSERT INTO follows (user_id, business_id) VALUES (?, ?)", (customer_a, business_id))
        conn.commit()
    finally:
        conn.close()

    tokens = {
        "owner": main.create_secure_session(owner),
        "customer_a": main.create_secure_session(customer_a),
        "customer_b": main.create_secure_session(customer_b),
    }
    with TestClient(main.app) as client:
        yield {"client": client, "tokens": tokens, "business_id": business_id}


def use_session(client, token):
    client.cookies.clear()
    client.cookies.set(main.SESSION_COOKIE_NAME, token)


def test_offer_change_notifies_only_followers(notification_client):
    client = notification_client["client"]
    use_session(client, notification_client["tokens"]["owner"])
    response = client.post(
        f"/api/businesses/{notification_client['business_id']}/offer",
        data={"offer": "10% off today"},
    )
    assert response.status_code == 200

    use_session(client, notification_client["tokens"]["customer_a"])
    own_notifications = client.get("/api/notifications")
    assert own_notifications.status_code == 200
    assert len(own_notifications.json()) == 1
    notification_id = own_notifications.json()[0]["id"]

    use_session(client, notification_client["tokens"]["customer_b"])
    assert client.get("/api/notifications").json() == []
    assert client.post(f"/api/notifications/{notification_id}/read").status_code == 404


def test_notifications_require_login_and_can_be_marked_read(notification_client):
    client = notification_client["client"]
    assert client.get("/api/notifications").status_code == 401

    use_session(client, notification_client["tokens"]["owner"])
    client.post(
        f"/api/businesses/{notification_client['business_id']}/offer",
        data={"offer": "Weekend offer"},
    )
    use_session(client, notification_client["tokens"]["customer_a"])
    response = client.get("/api/notifications")
    assert response.status_code == 200
    notification_id = response.json()[0]["id"]

    marked = client.post(f"/api/notifications/{notification_id}/read")
    assert marked.status_code == 200
    assert client.get("/api/notifications").json()[0]["read"] is True
