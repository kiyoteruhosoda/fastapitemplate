"""Search interface for application logs (implemented in the Infrastructure layer).

There is no write interface: writing to the ``log`` table is the job of the handler in
:mod:`shared.kernel.logging` (this context only reads).
"""

from __future__ import annotations

from typing import Protocol

from bounded_contexts.audit.domain.entities.application_log_entry import (
    ApplicationLogPage,
)
from bounded_contexts.audit.domain.value_objects.log_search_criteria import (
    ApplicationLogCriteria,
)


class ApplicationLogQuery(Protocol):
    def search(self, criteria: ApplicationLogCriteria) -> ApplicationLogPage:
        """Return one page of rows matching *criteria*, newest first (with the total count)."""


__all__ = ["ApplicationLogQuery"]
