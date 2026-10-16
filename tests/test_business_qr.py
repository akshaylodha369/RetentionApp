import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database
import main


@pytest.fixture
def qr_client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_NAME", str(tmp_path / "qr.db"))
    monkeypatch.setattr(database, "USE_POSTGRES", False)
    monkeypatch.setattr(main, "IS_PRODUCTION", False)
    monkeypatch.setattr(main, "_rate_limit_buckets", {})
    database.init_db()
    conn = database.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'owner')",
            ("Owner A", "owner-a@example.com", "test-hash"),
        )
        owner_a = cur.lastrowid
        cur.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'owner')",
            ("Owner B", "owner-b@example.com", "test-hash"),
        )
        owner_b = cur.lastrowid
        cur.execute(
            "INSERT INTO businesses (name, category, address, owner_id) VALUES (?, ?, ?, ?)",
            ("Cafe A", "cafe", "1 Main Road", owner_a),
        )
        business_a = cur.lastrowid
        cur.execute(
            "INSERT INTO businesses (name, category, address, owner_id) VALUES (?, ?, ?, ?)",
            ("Cafe B", "cafe", "2 Main Road", owner_b),
        )
        business_b = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    tokens = {
        "owner_a": main.create_secure_session(owner_a),
        "owner_b": main.create_secure_session(owner_b),
    }
    with TestClient(main.app) as client:
        yield {"client": client, "tokens": tokens, "business_a": business_a, "business_b": business_b}


def use_session(client, token):
    client.cookies.clear()
    client.cookies.set(main.SESSION_COOKIE_NAME, token)


def test_public_business_qr_returns_svg(qr_client):
    response = qr_client["client"].get(f"/api/businesses/{qr_client['business_a']}/qr.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert b"<svg" in response.content
    assert b"retentionapp.onrender.com/static/business.html?id=" in response.content


def test_owner_qr_requires_ownership(qr_client):
    client = qr_client["client"]
    assert client.get(f"/api/owner/businesses/{qr_client['business_a']}/qr.svg").status_code == 401
    use_session(client, qr_client["tokens"]["owner_a"])
    assert client.get(f"/api/owner/businesses/{qr_client['business_a']}/qr.svg").status_code == 200
    assert client.get(f"/api/owner/businesses/{qr_client['business_b']}/qr.svg").status_code == 403
