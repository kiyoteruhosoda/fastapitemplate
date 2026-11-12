"""Propagation of the request context (``requestId``, client address, acting principal).

Values set by the middleware and the authentication dependencies are kept in ``contextvars``.
There are two readers.

- Application logs: attached to every record automatically (``logging_config.RequestContextFilter``).
- Audit logs: recorded as the request context (the audit context's Presentation layer builds
  ``AuditRequestContext`` from here).

They are not passed around as arguments because logging and auditing are both cross-cutting
concerns, and threading request information through every function in between would bury their
actual responsibilities.
"""

from __future__ import annotations

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_hash_var: ContextVar[str | None] = ContextVar("user_id_hash", default=None)
# The "who" of audit logs. Set by the authentication dependency after verification (None for
# unauthenticated requests).
actor_user_id_var: ContextVar[int | None] = ContextVar("actor_user_id", default=None)
ip_address_var: ContextVar[str | None] = ContextVar("ip_address", default=None)
user_agent_var: ContextVar[str | None] = ContextVar("user_agent", default=None)


def current_request_id() -> str | None:
    return request_id_var.get()


def current_user_id_hash() -> str | None:
    return user_id_hash_var.get()


def current_actor_user_id() -> int | None:
    return actor_user_id_var.get()


def current_ip_address() -> str | None:
    return ip_address_var.get()


def current_user_agent() -> str | None:
    return user_agent_var.get()


__all__ = [
    "actor_user_id_var",
    "current_actor_user_id",
    "current_ip_address",
    "current_request_id",
    "current_user_agent",
    "current_user_id_hash",
    "ip_address_var",
    "request_id_var",
    "user_agent_var",
    "user_id_hash_var",
]
