import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database


def seed_owner_and_business():
    conn = database.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'owner')",
            ("Test Owner", "owner@example.com", "test-hash"),
        )
        owner_id = cur.lastrowid
        cur.execute(
            "INSERT INTO businesses (name, category, address, owner_id) VALUES (?, ?, ?, NULL)",
            ("Test Cafe", "cafe", "1 Test Road"),
        )
        business_id = cur.lastrowid
        conn.commit()
        return owner_id, business_id
    finally:
        conn.close()


def test_claim_request_approval_assigns_only_requested_business(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_NAME", str(tmp_path / "test.db"))
    database.init_db()
    owner_id, business_id = seed_owner_and_business()

    claim_id = database.create_business_claim_request(
        business_id, owner_id, "Verify official website", 100
    )
    assert claim_id > 0
    assert database.get_business_claim_requests(owner_id)[0][5] == "pending"
    pending = database.get_pending_business_claim_requests()
    assert pending[0][0] == claim_id
    assert pending[0][6] == "owner@example.com"

    result = database.review_business_claim_request(
        claim_id, "approved", 200, "manual-admin-review"
    )
    assert result["result"] == "approved"
    assert database.get_business_by_id(business_id)[7] == owner_id


def test_rejected_claim_can_be_resubmitted(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_NAME", str(tmp_path / "test.db"))
    database.init_db()
    owner_id, business_id = seed_owner_and_business()

    claim_id = database.create_business_claim_request(
        business_id, owner_id, "First attempt", 100
    )
    result = database.review_business_claim_request(
        claim_id, "rejected", 200, "manual-admin-review"
    )
    assert result["result"] == "rejected"

    same_claim_id = database.create_business_claim_request(
        business_id, owner_id, "Updated verification details", 300
    )
    assert same_claim_id == claim_id
    assert database.get_business_claim_requests(owner_id)[0][5] == "pending"


def test_claim_cannot_be_approved_after_business_is_already_assigned(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_NAME", str(tmp_path / "test.db"))
    database.init_db()
    owner_id, business_id = seed_owner_and_business()

    claim_id = database.create_business_claim_request(
        business_id, owner_id, "Verify", 100
    )
    conn = database.get_connection()
    try:
        conn.execute("UPDATE businesses SET owner_id = 999 WHERE id = ?", (business_id,))
        conn.commit()
    finally:
        conn.close()

    result = database.review_business_claim_request(
        claim_id, "approved", 200, "manual-admin-review"
    )
    assert result["result"] == "already_claimed"
    assert database.get_business_by_id(business_id)[7] == 999
