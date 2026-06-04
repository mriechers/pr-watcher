"""GitHub App authentication: mint JWT, exchange for installation token.

GitHub App auth has two layers:
1. App-level JWT (signed with the App's private key) — proves we are the App.
2. Installation token (short-lived, scoped to a single repo install) — used for
   actual API calls.

The JWT is only used to request an installation token; all subsequent API
calls use the installation token in the standard Authorization: Bearer header.
"""
from __future__ import annotations

import time

import httpx
import jwt as pyjwt

_GITHUB_API = "https://api.github.com"
_JWT_LIFETIME_SECONDS = 540  # 9 min — well under GH's 10-min ceiling, with slack for clock skew.
_TIMEOUT_SECONDS = 30


class GitHubAppError(RuntimeError):
    """Raised when GitHub returns a non-2xx response during App auth."""


def mint_jwt(*, app_id: str, private_key_pem: str) -> str:
    """Generate a short-lived JWT signed with the App's private key."""
    now = int(time.time())
    payload = {
        "iat": now - 30,  # 30s back-dating handles clock skew between us and GitHub.
        "exp": now + _JWT_LIFETIME_SECONDS,
        "iss": app_id,
    }
    return pyjwt.encode(payload, private_key_pem, algorithm="RS256")


def get_installation_token(
    *,
    app_id: str,
    private_key_pem: str,
    installation_id: str,
) -> str:
    """Exchange an App JWT for a repo-scoped installation access token."""
    jwt_token = mint_jwt(app_id=app_id, private_key_pem=private_key_pem)

    response = httpx.post(
        f"{_GITHUB_API}/app/installations/{installation_id}/access_tokens",
        headers={
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=_TIMEOUT_SECONDS,
    )

    if response.status_code >= 400:
        raise GitHubAppError(
            f"Installation token request failed ({response.status_code}): {response.text[:500]}"
        )

    return response.json()["token"]
