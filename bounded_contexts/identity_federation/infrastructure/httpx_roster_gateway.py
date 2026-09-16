"""assay の名簿を引く実装（ADR-0043。idp の ADR-0057 の口を叩く）。

```
GET {issuer}/admin/applications/self/users?subs=...
```

⚠ **経路にアプリを書かない。** どのアプリの名簿を返すかは、呼んできたサービスアカウント
（トークンの名乗り）から **assay が決める**。こちらが ``OIDC_CLIENT_ID`` を載せて
「自分はこのアプリだ」と申告する形は、nolumiawiki で作って向きが逆だと分かり捨てた
（nolumiawiki の ADR-0098）。

⚠ **403 は「このサービスアカウントがまだアプリの名乗りとして結び付いていない」。** 障害ではないので
:class:`MachineNotBoundToApplicationError` で分けて知らせる。

⚠ **引けなかったら例外で止める。** 空の名簿として返すと、呼び出し側は「全員辞めた」と
読んでしまう。
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

#: 一度に聞ける `sub` の数（idp の ADR-0057 の上限）。⚠ 超えると 400 になるので、分けて聞く。
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
                    # ⚠ 名乗らないと idp の前段の Cloudflare に落とされる。
                    "User-Agent": USER_AGENT,
                    "Authorization": f"Bearer {self.tokens.token()}",
                },
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as error:
            raise IdentityProviderUnavailableError(f"the roster is unreachable: {type(error).__name__}") from error
        if response.status_code == 401:
            # 期限内でも、向こうでクライアントを止めた・鍵を替えたときは通らなくなる。
            self.tokens.invalidate()
        if response.status_code == 403:
            # ⚠ 結び付けるまで毎周回ここへ来る。warning を撒かない（記録は呼び出し側で 1 行）。
            raise MachineNotBoundToApplicationError("the machine client is not bound to an application")
        if response.status_code != 200:
            # ⚠ 名簿が空なのとは違うので、**ここで止める**。
            logger.warning("sso_roster_request_failed", extra={"status_code": response.status_code})
            raise IdentityProviderUnavailableError(f"the roster returned {response.status_code}")
        try:
            body = response.json()
        except ValueError as error:
            raise IdentityProviderUnavailableError("the roster response is not JSON") from error
        return body if isinstance(body, dict) else {}


__all__ = ["SUBJECTS_PER_REQUEST", "HttpxRosterGateway"]
