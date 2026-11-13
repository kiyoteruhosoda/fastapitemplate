"""Implementation that fetches assay's roster (ADR-0077 §7. Calls idp's ADR-0057 endpoint).

```
GET {issuer}/admin/applications/self/users?subs=...
```

⚠ **Don't put the app in the path.** Which app's roster to return is decided **by assay** from the
calling service account (the token's identity). Declaring "I am this app" by sending ``OIDC_CLIENT_ID``
was built in nolumiawiki, found to be backwards, and dropped
(nolumiawiki ADR-0098).

⚠ **403 means "this service account is not yet bound as the app's identity".** Not a fault, so
it is reported separately as :class:`MachineNotBoundToApplicationError`.

⚠ **Stop with an exception when the lookup fails.** Returning an empty roster would make the caller
read it as "everyone left".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

from bounded_contexts.identity_federation.domain.exceptions import (
    IdentityProviderUnavailableError,
    MachineNotBoundToApplicationError,
    SsoNotConfiguredError,
)
from bounded_contexts.identity_federation.domain.value_objects.roster import (
    Roster,
    RosterEntry,
)
from bounded_contexts.identity_federation.infrastructure.assay_admin_token import (
    AdminToken,
    AssayAdminTokenSource,
)
from bounded_contexts.identity_federation.infrastructure.oidc_metadata import USER_AGENT
from shared.kernel.settings.settings import settings

logger = logging.getLogger(__name__)

#: Number of `sub` values per query (idp ADR-0057 limit). ⚠ Exceeding it gives 400, so ask in batches.
SUBJECTS_PER_REQUEST = 100

_REQUEST_TIMEOUT_SECONDS = 10.0


@dataclass
class HttpxRosterGateway:
    tokens: AdminToken = field(default_factory=AssayAdminTokenSource)

    def fetch(self, *, subjects: tuple[str, ...]) -> Roster:
        issuer = settings.oidc_issuer
        if not issuer:
            raise SsoNotConfiguredError("OIDC_ISSUER is not configured")
        entries: list[RosterEntry] = []
        for index in range(0, len(subjects), SUBJECTS_PER_REQUEST):
            entries.extend(self._fetch_chunk(issuer, subjects[index : index + SUBJECTS_PER_REQUEST]))
        return Roster(entries=tuple(entries))

    def _fetch_chunk(self, issuer: str, subjects: tuple[str, ...]) -> list[RosterEntry]:
        url = f"{issuer.rstrip('/')}/admin/applications/self/users"
        payload = self._get(url, params={"subs": ",".join(subjects)})
        users = payload.get("users")
        if not isinstance(users, list):
            raise IdentityProviderUnavailableError("the roster response has no users")
        return [entry for entry in (RosterEntry.of(user) for user in users if isinstance(user, dict)) if entry]

    def _get(self, url: str, *, params: dict[str, str]) -> dict[str, object]:
        try:
            response = httpx.get(
                url,
                params=params,
                headers={
                    "Accept": "application/json",
                    # ⚠ Without identifying itself, Cloudflare in front of idp drops it.
                    "User-Agent": USER_AGENT,
                    "Authorization": f"Bearer {self.tokens.token()}",
                },
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as error:
            raise IdentityProviderUnavailableError(f"the roster is unreachable: {type(error).__name__}") from error
        if response.status_code == 401:
            # Even within expiry, it stops passing if the client was stopped or the key changed over there.
            self.tokens.invalidate()
        if response.status_code == 403:
            # ⚠ This is hit every cycle until bound. Don't spray warnings (the caller logs one line).
            raise MachineNotBoundToApplicationError("the machine client is not bound to an application")
        if response.status_code != 200:
            # ⚠ Not the same as an empty roster, so **stop here**.
            logger.warning("sso_roster_request_failed", extra={"status_code": response.status_code})
            raise IdentityProviderUnavailableError(f"the roster returned {response.status_code}")
        try:
            body = response.json()
        except ValueError as error:
            raise IdentityProviderUnavailableError("the roster response is not JSON") from error
        return body if isinstance(body, dict) else {}


__all__ = ["SUBJECTS_PER_REQUEST", "HttpxRosterGateway"]
