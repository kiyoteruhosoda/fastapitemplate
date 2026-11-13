"""audit context -- records "what happened" so it can be verified later.

It handles two kinds of records. Both can be matched by ``requestId``.

============== ================= ==================================================
Record         Table             What it keeps
============== ================= ==================================================
Audit log      ``audit_log``     **Who did what** (sign-in, user management, setting changes)
App log        ``log``           **What the system did** (requests, warnings, exceptions)
============== ================= ==================================================

Responsibility for writing is split.

- Audit log: written by this context (``application/use_cases/record_audit_event.py``).
- App log: a cross-cutting concern, written by ``DbLogHandler`` in :mod:`shared.kernel.logging`.
  This context **only reads** it.

Neither contains PII. Details in ``docs/decisions/ADR-0075-logs-and-audit.md``.
"""
