"""Generation of single-use values for the login round trip, and their stored form.

``state`` / ``nonce`` / PKCE ``code_verifier`` / redemption tickets all share the single
requirement of "unguessable", so there's no reason to vary how they are generated.
They are gathered in one place.

A redemption ticket is a credential handed to its holder, so only its SHA-256 hash goes into
the DB (so a leaked copy can't be used to sign in directly).
"""

from __future__ import annotations

import base64
import hashlib
import secrets

# 128 bits or more makes brute force impractical. RFC 7636 requires 43–128 characters for
# code_verifier, and 32 bytes of base64url (43 characters) meets that minimum.
_TOKEN_BYTES = 32


def new_secret() -> str:
    """Create an unguessable URL-safe string (state / nonce / redemption ticket)."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def new_code_verifier() -> str:
    """PKCE ``code_verifier`` (RFC 7636)."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def code_challenge_of(code_verifier: str) -> str:
    """Create the ``S256`` ``code_challenge`` from the ``code_verifier``.

    ``plain`` is not used: anyone able to see the authorization request would get the
    verifier as is, defeating PKCE.
    """
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def hash_secret(value: str) -> str:
    """Hash for storage. Comparisons are always hash to hash."""
    return hashlib.sha256(value.encode()).hexdigest()


__all__ = ["code_challenge_of", "hash_secret", "new_code_verifier", "new_secret"]
