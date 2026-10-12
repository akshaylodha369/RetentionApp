import sys
from types import SimpleNamespace

import database


class FakeCursor:
    def __init__(self):
        self.statements = []
        self.rows = [(42,)]
        self.rowcount = 1

    def execute(self, statement, params):
        self.statements.append((statement, params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        return []


class FakeIntegrityError(Exception):
    pass


def test_postgres_cursor_translates_placeholders_and_returns_inserted_id(monkeypatch):
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(IntegrityError=FakeIntegrityError))
    raw = FakeCursor()
    cursor = database.PostgresCursor(raw)

    cursor.execute("INSERT INTO users (name, email) VALUES (?, ?)", ("A", "a@example.com"))

    statement, params = raw.statements[0]
    assert statement == "INSERT INTO users (name, email) VALUES (%s, %s) RETURNING id"
    assert params == ("A", "a@example.com")
    assert cursor.lastrowid == 42


def test_postgres_cursor_translates_insert_or_ignore(monkeypatch):
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(IntegrityError=FakeIntegrityError))
    raw = FakeCursor()
    cursor = database.PostgresCursor(raw)

    cursor.execute("INSERT OR IGNORE INTO follows (user_id, business_id) VALUES (?, ?)", (1, 2))

    statement, params = raw.statements[0]
    assert statement == "INSERT INTO follows (user_id, business_id) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING id"
    assert params == (1, 2)
    assert cursor.lastrowid == 42


def test_postgres_cursor_translates_immediate_begin(monkeypatch):
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(IntegrityError=FakeIntegrityError))
    raw = FakeCursor()
    cursor = database.PostgresCursor(raw)

    cursor.execute("BEGIN IMMEDIATE")

    assert raw.statements[0] == ("BEGIN", ())
