import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


class FakeResponse:
    def __init__(self):
        self.headers = {}


def test_baseline_security_headers_are_added():
    response = FakeResponse()
    main.apply_security_headers(response)

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=(self)"
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"


def test_existing_header_values_are_not_overwritten():
    response = FakeResponse()
    response.headers["X-Frame-Options"] = "SAMEORIGIN"

    main.apply_security_headers(response)

    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"


def test_hsts_is_enabled_only_in_production(monkeypatch):
    response = FakeResponse()
    monkeypatch.setattr(main, "IS_PRODUCTION", False)
    main.apply_security_headers(response)
    assert "Strict-Transport-Security" not in response.headers

    response = FakeResponse()
    monkeypatch.setattr(main, "IS_PRODUCTION", True)
    main.apply_security_headers(response)
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000"
