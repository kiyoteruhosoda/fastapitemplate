"""Check the signing key at startup (ADR-0073 §4).

**In production (``APP_ENV=production``) the app does not start with the default key.** The
default value is in a public repository, so anyone can forge tokens issued with it. Moreover,
access token verification does not hit the DB (ADR-0076 §5), so a forged token passes with
whatever permissions it claims. A warning only shows up in the log, and nobody reads production
logs every day. The only reliable way to make it noticed is to refuse to run.

In other environments it only warns and starts. Nobody in development suffers from a forgeable key.

The key value itself is never logged. Only the category (empty, still default, too short) is.
"""

from __future__ import annotations

import logging

from shared.kernel.settings.system_settings_defaults import DEFAULT_APPLICATION_SETTINGS

logger = logging.getLogger(__name__)

#: Environment name (``APP_ENV``) that refuses to run with the default value
PRODUCTION = "production"
#: Equivalent to 256 bits in base64. ``openssl rand -base64 48`` gives 64 characters
MIN_SECRET_LENGTH = 32


class InsecureSecretError(RuntimeError):
    """A signing key unusable in production. Raised to stop startup."""


def secret_problem(secret: str) -> str | None:
    """Category of what is wrong with the key. ``None`` if there is no problem.

    "Not the default" does not mean "strong". The length is checked too.
    """
    if not secret:
        return "empty"
    if secret == DEFAULT_APPLICATION_SETTINGS["JWT_SECRET_KEY"]:
        return "default"
    if len(secret) < MIN_SECRET_LENGTH:
        return "too_short"
    return None


def require_usable_secret(secret: str, environment: str) -> None:
    """In production, fail on a bad key; otherwise warn."""
    problem = secret_problem(secret)
    if problem is None:
        return
    if environment == PRODUCTION:
        logger.critical(
            "the signing key is not fit for production: %s. Generate a JWT_SECRET_KEY and set it",
            problem,
            extra={"event": "startup.insecure_secret", "problem": problem},
        )
        raise InsecureSecretError(f"JWT_SECRET_KEY is {problem}; refusing to start in {environment}")
    logger.warning(
        "the signing key is not fit for production (%s). "
        "Starting anyway because this is development; production stops here",
        problem,
        extra={"event": "startup.insecure_secret", "problem": problem},
    )


__all__ = ["MIN_SECRET_LENGTH", "PRODUCTION", "InsecureSecretError", "require_usable_secret", "secret_problem"]
