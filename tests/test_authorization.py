import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database
import main


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_NAME", str(tmp_path / "authorization.db"))
    monkeypatch.setattr(database, "USE_POSTGRES", False)
    monkeypatch.setattr(main, "IS_PRODUCTION", False)
    monkeypatch.setattr(main, "_rate_limit_buckets", {})
    database.init_db()

    def add_user(name, email, role):
        conn = database.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
                (name, email, "test-hash", role),
            )
            user_id = cursor.lastrowid
            conn.commit()
            return user_id
        finally:
            conn.close()

    def add_business(name, owner_id=None):
        conn = database.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO businesses (name, category, address, owner_id) VALUES (?, 'cafe', ?, ?)",
                (name, f"{name} address", owner_id),
            )
            business_id = cursor.lastrowid
            conn.commit()
            return business_id
        finally:
            conn.close()

    owner_a = add_user("Owner A", "owner-a@example.com", "owner")
    owner_b = add_user("Owner B", "owner-b@example.com", "owner")
    customer = add_user("Customer", "customer@example.com", "customer")
    business_a = add_business("Cafe A", owner_a)
    business_b = add_business("Cafe B", owner_b)
    unclaimed_business = add_business("Unclaimed Cafe")

    tokens = {
        "owner_a": main.create_secure_session(owner_a),
        "owner_b": main.create_secure_session(owner_b),
        "customer": main.create_secure_session(customer),
    }

    with TestClient(main.app) as client:
        yield {
            "client": client,
            "tokens": tokens,
            "owner_a": owner_a,
            "owner_b": owner_b,
            "customer": customer,
            "business_a": business_a,
            "business_b": business_b,
            "unclaimed_business": unclaimed_business,
        }


def use_session(client, token):
    client.cookies.clear()
    client.cookies.set(main.SESSION_COOKIE_NAME, token)


def test_private_endpoints_reject_anonymous_users(app_client):
    client = app_client["client"]
    response = client.get("/api/following")
    assert response.status_code == 401

    response = client.get("/api/owner/businesses")
    assert response.status_code == 401


def test_customer_cannot_access_owner_endpoints(app_client):
    client = app_client["client"]
    use_session(client, app_client["tokens"]["customer"])

    assert client.get("/api/owner/businesses").status_code == 403
    assert client.get("/api/owner/business-claims").status_code == 403
    response = client.post(
        f"/api/businesses/{app_client['business_a']}/offer",
        data={"offer": "Unauthorized change"},
    )
    assert response.status_code == 403


def test_owner_can_only_see_businesses_assigned_to_them(app_client):
    client = app_client["client"]
    use_session(client, app_client["tokens"]["owner_a"])

    response = client.get("/api/owner/businesses")
    assert response.status_code == 200
    business_ids = {business["id"] for business in response.json()}
    assert business_ids == {app_client["business_a"]}
    assert app_client["business_b"] not in business_ids


def test_owner_cannot_change_another_owners_offer(app_client):
    client = app_client["client"]
    use_session(client, app_client["tokens"]["owner_a"])

    response = client.post(
        f"/api/businesses/{app_client['business_b']}/offer",
        data={"offer": "Changed by wrong owner"},
    )
    assert response.status_code == 403
    assert database.get_business_by_id(app_client["business_b"])[6] is None


def test_owner_claim_list_is_scoped_to_the_authenticated_owner(app_client):
    client = app_client["client"]
    use_session(client, app_client["tokens"]["owner_a"])

    response = client.post(
        "/api/owner/business-claims",
        data={"business_id": app_client["unclaimed_business"], "note": "I own this cafe"},
    )
    assert response.status_code == 200

    own_claims = client.get("/api/owner/business-claims")
    assert own_claims.status_code == 200
    assert len(own_claims.json()) == 1
    assert own_claims.json()[0]["business_id"] == app_client["unclaimed_business"]

    use_session(client, app_client["tokens"]["owner_b"])
    other_claims = client.get("/api/owner/business-claims")
    assert other_claims.status_code == 200
    assert other_claims.json() == []


def test_logout_revokes_server_side_session(app_client):
    client = app_client["client"]
    token = app_client["tokens"]["customer"]
    use_session(client, token)

    assert client.get("/api/me").json()["logged_in"] is True
    logout_response = client.post("/api/logout")
    assert logout_response.status_code == 200

    # Even if a copied old token is supplied again, the server must reject it.
    use_session(client, token)
    response = client.get("/api/me")
    assert response.status_code == 200
    assert response.json()["logged_in"] is False


def test_admin_claim_endpoint_fails_closed_without_secret(app_client, monkeypatch):
    monkeypatch.delenv("BUSINESS_MIGRATION_SECRET", raising=False)
    response = app_client["client"].get("/api/admin/business-claims")
    assert response.status_code == 404


def test_public_business_apis_do_not_expose_internal_owner_ids(app_client):
    client = app_client["client"]

    all_businesses = client.get("/api/businesses")
    assert all_businesses.status_code == 200
    assert all("owner_id" not in business for business in all_businesses.json())

    business_detail = client.get(
        f"/api/businesses/{app_client['business_a']}"
    )
    assert business_detail.status_code == 200
    assert "owner_id" not in business_detail.json()


def test_signup_rejects_email_already_used_by_another_role(app_client):
    response = app_client["client"].post(
        "/api/owner/signup",
        data={
            "name": "Duplicate Owner",
            "email": "customer@example.com",
            "password": "safe-password-123",
        },
    )
    assert response.status_code == 409


def test_unknown_login_email_still_runs_password_hash_check(app_client, monkeypatch):
    calls = []
    original_verify = main.verify_password

    def record_verify(password, stored_hash):
        calls.append(stored_hash)
        return original_verify(password, stored_hash)

    monkeypatch.setattr(main, "verify_password", record_verify)
    response = app_client["client"].post(
        "/api/login",
        data={"email": "missing@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert calls == [main.DUMMY_PASSWORD_HASH]


def test_session_database_stores_only_token_hashes(app_client):
    token = app_client["tokens"]["customer"]
    conn = database.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT token_hash FROM sessions")
        stored_hashes = {row[0] for row in cursor.fetchall()}
    finally:
        conn.close()

    import hashlib
    assert token not in stored_hashes
    assert hashlib.sha256(token.encode("utf-8")).hexdigest() in stored_hashes
