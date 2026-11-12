"""Return from the IdP (``code`` / ``state`` and the round-trip state restored from the browser).

Login completion and link completion (ADR-0077 §5) receive the same three, so they are bundled as a value.
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.domain.value_objects.login_transaction import (
    LoginTransaction,
)


@dataclass(frozen=True)
class SsoCallback:
    code: str
    state: str
    #: ``None`` if it couldn't be restored (the receiver refuses).
    transaction: LoginTransaction | None


__all__ = ["SsoCallback"]
