"""What the authorization request was started for (ADR-0077 §5).

Round trips to the IdP serve three purposes — **signing in** (login), **binding to oneself
while already signed in** (linking), and **continuing an expired login** (ADR-0104). Only one
redirect URI is registered, so ``/callback`` looks at this value to decide which follow-up to run.

⚠ **The purpose goes into the round-trip state (signed cookie).** Put in the query, rewriting
the return URL alone would turn "a round trip started as a login" into "a link".
"""

from __future__ import annotations

from enum import StrEnum


class TransactionPurpose(StrEnum):
    #: Round trip for signing in. The return becomes a redemption ticket.
    LOGIN = "login"
    #: Round trip for binding to an already signed-in user (ADR-0077 §5).
    LINK = "link"
    #: Round trip that silently continues an expired login (inside a hidden frame. ADR-0104).
    #: The return sets cookies without a redemption ticket and sends to the result page.
    RENEW = "renew"


__all__ = ["TransactionPurpose"]
