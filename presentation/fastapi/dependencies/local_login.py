"""Check whether the local entrance is open (ADR-0076 §3 decisions 2 and 3).

When ``LOCAL_LOGIN_ENABLED`` is ``false``, password and passkey login and
**registration of local credentials** (passkey, TOTP, password change) are blocked.

Registration is blocked too so nobody can make a spare key to a closed entrance. If a user
who came in via SSO could add a passkey, that key would work the moment the setting is
reverted. With the rule "entrance closed = no new keys for it", operators need not think
beyond "it is closed".

**Credentials already registered are not deleted.** Deleting them on close would lock
everyone out when it is reopened.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from shared.kernel.settings.settings import settings

ERROR_CODE = "local_login_disabled"


def require_local_login() -> None:
    """Reject with 403 if the local entrance is closed (for ``Depends()``)."""
    if not settings.local_login_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": ERROR_CODE},
        )


__all__ = ["ERROR_CODE", "require_local_login"]
