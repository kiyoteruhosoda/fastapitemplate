"""Second factors held on this app's side (ADR-0076 §7).

⚠ **These are separate from the IdP's multi-factor.** Requiring multi-factor at the IdP does not
apply here — that is what having two authentication systems means; read the inventory with that in mind.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LocalFactors:
    #: Whether two-factor authentication (TOTP) is **enabled** (not counted while enrollment is in progress).
    totp: bool = False
    #: Number of registered passkeys.
    passkeys: int = 0


__all__ = ["LocalFactors"]
