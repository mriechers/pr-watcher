"""Tests for GitHub App authentication."""
from __future__ import annotations

import time

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from pr_review import github_app


@pytest.fixture
def rsa_private_key_pem() -> str:
    """Generate an RSA keypair for tests; return the private key as PEM."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def test_mint_jwt_returns_valid_signed_token(rsa_private_key_pem):
    token = github_app.mint_jwt(app_id="12345", private_key_pem=rsa_private_key_pem)

    decoded = pyjwt.decode(token, options={"verify_signature": False})
    assert decoded["iss"] == "12345"
    now = int(time.time())
    assert decoded["iat"] <= now + 5
    assert decoded["exp"] > now


def test_mint_jwt_expiry_within_ten_minutes(rsa_private_key_pem):
    """GitHub rejects App JWTs older than 10 minutes — keep expiry short."""
    token = github_app.mint_jwt(app_id="12345", private_key_pem=rsa_private_key_pem)
    decoded = pyjwt.decode(token, options={"verify_signature": False})
    lifetime = decoded["exp"] - decoded["iat"]
    assert lifetime <= 600  # ≤10 min
    assert lifetime >= 60   # ≥1 min (any shorter is too brittle for clock skew)


def test_get_installation_token_calls_correct_endpoint(httpx_mock, rsa_private_key_pem):
    httpx_mock.add_response(
        url="https://api.github.com/app/installations/99/access_tokens",
        method="POST",
        json={"token": "ghs_test_token_abc", "expires_at": "2026-05-13T20:00:00Z"},
        status_code=201,
    )

    token = github_app.get_installation_token(
        app_id="12345",
        private_key_pem=rsa_private_key_pem,
        installation_id="99",
    )

    assert token == "ghs_test_token_abc"
    request = httpx_mock.get_request()
    assert request.headers["Authorization"].startswith("Bearer ")
    assert request.headers["Accept"] == "application/vnd.github+json"


def test_get_installation_token_raises_on_error(httpx_mock, rsa_private_key_pem):
    httpx_mock.add_response(
        url="https://api.github.com/app/installations/99/access_tokens",
        method="POST",
        status_code=404,
        json={"message": "Not Found"},
    )

    with pytest.raises(github_app.GitHubAppError):
        github_app.get_installation_token(
            app_id="12345",
            private_key_pem=rsa_private_key_pem,
            installation_id="99",
        )
