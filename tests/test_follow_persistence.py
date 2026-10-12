import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database


def seed_user_and_business():
    conn = database.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'customer')",
            ("Follow Tester", "follow-tester@example.com", "test-hash"),
        )
        user_id = cur.lastrowid
        cur.execute(
            "INSERT INTO businesses (name, category, address) VALUES (?, ?, ?)",
            ("Follow Test Cafe", "cafe", "1 Follow Road"),
        )
        business_id = cur.lastrowid
        conn.commit()
        return user_id, business_id
    finally:
        conn.close()


def test_follow_is_persistent_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_NAME", str(tmp_path / "follow.db"))
    monkeypatch.setattr(database, "USE_POSTGRES", False)
    database.init_db()
    user_id, business_id = seed_user_and_business()

    database.follow_business(user_id, business_id)
    database.follow_business(user_id, business_id)

    assert database.is_following(user_id, business_id) is True
    followed = database.get_followed_businesses(user_id)
    assert len(followed) == 1
    assert followed[0][0] == business_id

    # The relation must survive a fresh database connection.
    assert database.is_following(user_id, business_id) is True


def test_unfollow_removes_only_that_users_follow(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_NAME", str(tmp_path / "unfollow.db"))
    monkeypatch.setattr(database, "USE_POSTGRES", False)
    database.init_db()
    user_a, business_id = seed_user_and_business()

    conn = database.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'customer')",
            ("Other User", "other-follow-tester@example.com", "test-hash"),
        )
        user_b = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    database.follow_business(user_a, business_id)
    database.follow_business(user_b, business_id)
    database.unfollow_business(user_a, business_id)

    assert database.is_following(user_a, business_id) is False
    assert database.is_following(user_b, business_id) is True
