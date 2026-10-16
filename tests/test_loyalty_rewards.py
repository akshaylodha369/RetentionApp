import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database
import main


@pytest.fixture
def loyalty_client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_NAME", str(tmp_path / "loyalty.db"))
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

    owner = add_user("Cafe Owner", "owner@example.com", "owner")
    other_owner = add_user("Other Owner", "other@example.com", "owner")
    customer = add_user("Customer", "customer@example.com", "customer")

    conn = database.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO businesses (name, category, address, owner_id) VALUES (?, ?, ?, ?)",
            ("Test Cafe", "cafe", "1 Main Road", owner),
        )
        business_id = cur.lastrowid
        cur.execute(
            "INSERT INTO businesses (name, category, address, owner_id) VALUES (?, ?, ?, ?)",
            ("Other Cafe", "cafe", "2 Main Road", other_owner),
        )
        other_business_id = cur.lastrowid
        cur.execute(
            "INSERT INTO follows (user_id, business_id) VALUES (?, ?)",
            (customer, business_id),
        )
        conn.commit()
    finally:
        conn.close()

    tokens = {
        "owner": main.create_secure_session(owner),
        "other_owner": main.create_secure_session(other_owner),
        "customer": main.create_secure_session(customer),
    }

    with TestClient(main.app) as client:
        yield {
            "client": client,
            "tokens": tokens,
            "owner": owner,
            "other_owner": other_owner,
            "customer": customer,
            "business_id": business_id,
            "other_business_id": other_business_id,
        }


def use_session(client, token):
    client.cookies.clear()
    client.cookies.set(main.SESSION_COOKIE_NAME, token)


def test_owner_can_create_reward_only_for_owned_business(loyalty_client):
    client = loyalty_client["client"]
    use_session(client, loyalty_client["tokens"]["owner"])

    response = client.post(
        f"/api/owner/businesses/{loyalty_client['business_id']}/rewards",
        data={"title": "Free coffee", "description": "One small coffee", "points_cost": 50},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

    response = client.post(
        f"/api/owner/businesses/{loyalty_client['other_business_id']}/rewards",
        data={"title": "Unauthorized", "points_cost": 10},
    )
    assert response.status_code == 403


def test_owner_can_award_points_only_to_a_following_customer(loyalty_client):
    client = loyalty_client["client"]
    use_session(client, loyalty_client["tokens"]["owner"])

    response = client.post(
        f"/api/owner/businesses/{loyalty_client['business_id']}/points",
        data={
            "customer_email": "customer@example.com",
            "points": 100,
            "reason": "Purchase receipt 1001",
        },
    )
    assert response.status_code == 200
    assert response.json()["points_awarded"] == 100

    second_award = client.post(
        f"/api/owner/businesses/{loyalty_client['business_id']}/points",
        data={
            "customer_email": "customer@example.com",
            "points": 10,
            "reason": "Purchase receipt 1001B",
        },
    )
    assert second_award.status_code == 200
    analytics = client.get("/api/owner/analytics").json()["businesses"][0]
    assert analytics["customers_rewarded"] == 1
    assert analytics["repeat_customers"] == 1

    response = client.post(
        f"/api/owner/businesses/{loyalty_client['other_business_id']}/points",
        data={
            "customer_email": "customer@example.com",
            "points": 100,
            "reason": "Attempt on another business",
        },
    )
    assert response.status_code == 403


def test_customer_can_redeem_reward_and_owner_can_fulfill_it(loyalty_client):
    client = loyalty_client["client"]
    use_session(client, loyalty_client["tokens"]["owner"])
    created = client.post(
        f"/api/owner/businesses/{loyalty_client['business_id']}/rewards",
        data={"title": "Free coffee", "description": "One small coffee", "points_cost": 50},
    )
    assert created.status_code == 200
    reward_id = created.json()["reward_id"]

    awarded = client.post(
        f"/api/owner/businesses/{loyalty_client['business_id']}/points",
        data={
            "customer_email": "customer@example.com",
            "points": 100,
            "reason": "Purchase receipt 1002",
        },
    )
    assert awarded.status_code == 200

    use_session(client, loyalty_client["tokens"]["customer"])
    redeemed = client.post(f"/api/rewards/{reward_id}/redeem")
    assert redeemed.status_code == 200
    assert redeemed.json()["remaining_points"] == 50
    redemption_id = redeemed.json()["redemption_id"]

    use_session(client, loyalty_client["tokens"]["owner"])
    fulfilled = client.post(f"/api/owner/redemptions/{redemption_id}/fulfill")
    assert fulfilled.status_code == 200
    assert fulfilled.json()["status"] == "fulfilled"
    assert client.post(f"/api/owner/redemptions/{redemption_id}/fulfill").status_code == 404


def test_customer_cannot_redeem_without_enough_points(loyalty_client):
    client = loyalty_client["client"]
    use_session(client, loyalty_client["tokens"]["owner"])
    created = client.post(
        f"/api/owner/businesses/{loyalty_client['business_id']}/rewards",
        data={"title": "Big reward", "points_cost": 500},
    )
    assert created.status_code == 200

    use_session(client, loyalty_client["tokens"]["customer"])
    response = client.post(f"/api/rewards/{created.json()['reward_id']}/redeem")
    assert response.status_code == 409


def test_loyalty_summary_is_private_and_scoped_to_logged_in_customer(loyalty_client):
    client = loyalty_client["client"]
    assert client.get("/api/loyalty/summary").status_code == 401

    use_session(client, loyalty_client["tokens"]["owner"])
    assert client.get("/api/loyalty/summary").status_code == 200
    assert client.get("/api/owner/analytics").status_code == 200

    use_session(client, loyalty_client["tokens"]["customer"])
    summary = client.get("/api/loyalty/summary")
    assert summary.status_code == 200
    assert summary.json()["balances"] == []


def test_owner_can_update_and_deactivate_only_own_reward(loyalty_client):
    client = loyalty_client["client"]
    use_session(client, loyalty_client["tokens"]["owner"])
    created = client.post(
        f"/api/owner/businesses/{loyalty_client['business_id']}/rewards",
        data={"title": "Starter", "description": "Initial", "points_cost": 25},
    )
    assert created.status_code == 200
    reward_id = created.json()["reward_id"]

    updated = client.post(
        f"/api/owner/rewards/{reward_id}/update",
        data={"title": "Updated reward", "description": "Updated details", "points_cost": 40},
    )
    assert updated.status_code == 200
    assert client.get(f"/api/businesses/{loyalty_client['business_id']}/rewards").json()[0]["title"] == "Updated reward"

    use_session(client, loyalty_client["tokens"]["other_owner"])
    assert client.post(f"/api/owner/rewards/{reward_id}/deactivate").status_code == 404

    use_session(client, loyalty_client["tokens"]["owner"])
    assert client.post(f"/api/owner/rewards/{reward_id}/deactivate").status_code == 200
    assert client.get(f"/api/businesses/{loyalty_client['business_id']}/rewards").json() == []


def test_customer_can_view_only_their_own_redemption_history(loyalty_client):
    client = loyalty_client["client"]
    use_session(client, loyalty_client["tokens"]["owner"])
    created = client.post(
        f"/api/owner/businesses/{loyalty_client['business_id']}/rewards",
        data={"title": "Small reward", "points_cost": 20},
    )
    assert created.status_code == 200
    awarded = client.post(
        f"/api/owner/businesses/{loyalty_client['business_id']}/points",
        data={"customer_email": "customer@example.com", "points": 40, "reason": "Receipt #77"},
    )
    assert awarded.status_code == 200

    use_session(client, loyalty_client["tokens"]["customer"])
    redeemed = client.post(f"/api/rewards/{created.json()['reward_id']}/redeem")
    assert redeemed.status_code == 200
    history = client.get("/api/loyalty/redemptions")
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["status"] == "pending"
