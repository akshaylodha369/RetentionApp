import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


def test_same_origin_request_accepts_production_https_origin():
    assert main.is_same_origin_request(
        "https://retentionapp.onrender.com",
        "retentionapp.onrender.com",
        True,
    )


def test_same_origin_request_rejects_other_host():
    assert not main.is_same_origin_request(
        "https://attacker.example",
        "retentionapp.onrender.com",
        True,
    )


def test_same_origin_request_rejects_http_in_production():
    assert not main.is_same_origin_request(
        "http://retentionapp.onrender.com",
        "retentionapp.onrender.com",
        True,
    )


def test_same_origin_request_accepts_local_http_development():
    assert main.is_same_origin_request(
        "http://localhost:8000",
        "localhost:8000",
        False,
    )


def test_same_origin_request_rejects_malformed_or_missing_origin():
    assert not main.is_same_origin_request(
        "not a url",
        "retentionapp.onrender.com",
        True,
    )
    assert not main.is_same_origin_request(
        "",
        "retentionapp.onrender.com",
        True,
    )
