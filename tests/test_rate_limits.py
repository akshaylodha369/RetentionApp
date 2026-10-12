import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


def test_login_rate_limit_allows_limit_then_blocks(monkeypatch):
    monkeypatch.setattr(main, "_rate_limit_buckets", {})
    path = "/api/login"

    for attempt in range(main.RATE_LIMITS[path]):
        assert main.check_rate_limit(path, "192.0.2.10", now=100) is None

    retry_after = main.check_rate_limit(path, "192.0.2.10", now=101)
    assert retry_after == main.RATE_LIMIT_WINDOW_SECONDS - 1


def test_rate_limits_are_separate_by_endpoint_and_client(monkeypatch):
    monkeypatch.setattr(main, "_rate_limit_buckets", {})

    for attempt in range(main.RATE_LIMITS["/api/signup"]):
        assert main.check_rate_limit("/api/signup", "192.0.2.10", now=100) is None

    assert main.check_rate_limit("/api/signup", "192.0.2.10", now=101) is not None
    assert main.check_rate_limit("/api/login", "192.0.2.10", now=101) is None
    assert main.check_rate_limit("/api/signup", "192.0.2.11", now=101) is None


def test_rate_limit_resets_after_window(monkeypatch):
    monkeypatch.setattr(main, "_rate_limit_buckets", {})
    path = "/api/owner/login"

    for attempt in range(main.RATE_LIMITS[path]):
        assert main.check_rate_limit(path, "192.0.2.10", now=100) is None

    assert main.check_rate_limit(path, "192.0.2.10", now=100) is not None
    assert main.check_rate_limit(
        path, "192.0.2.10", now=100 + main.RATE_LIMIT_WINDOW_SECONDS
    ) is None


def test_unprotected_routes_are_not_rate_limited(monkeypatch):
    monkeypatch.setattr(main, "_rate_limit_buckets", {})
    for _ in range(25):
        assert main.check_rate_limit("/api/me", "192.0.2.10", now=100) is None
