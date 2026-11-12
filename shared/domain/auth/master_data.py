"""Source of truth for authorization master data (ubiquitous language: role / permission / grant).

Roles, permission codes, grants of permissions to roles and the initial administrator are
"master data" the application needs to work correctly from startup. To prevent drift from
duplicated definitions, this is the single source of truth, referenced by both

- the migrations (``migrations/versions/*_seed_master_data.py``)
- the seed script (``scripts/seed_master_data.py``)

It is pure data with no framework or DB dependency, so it can be imported safely from anywhere.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

# --- Roles ---------------------------------------------------------------------
# ids are fixed as stable keys for external references (user_roles etc.).
#
# Roles are split by the family of "what they handle" (ADR-0078 §4).
#
# One role corresponds to one actor (a person who uses the system) (ADR-0084).
#
# Outside the tenants (ADR-0079 §1). Held only by users who belong to no tenant.
# - Operator:          system-admin (register/suspend/delete tenants, global settings, restart, app logs)
# - Support staff:     system-support (only views the tenant list and status, and system status)
#
# Inside a tenant. Effective only within one's own tenant.
# - Tenant admin:      owner (all permissions inside; ADR-0078 §5)
# - User admin:        user-admin (manages users and groups, and grants/revokes roles within own scope)
# - Content admin:     content-admin (decides content settings; only reads the content itself)
# - Editor:            manager (creates, edits and deletes content)
# - Viewer:            member (reads) / guest (can only sign in)
# - Auditor:           auditor (only views audit logs and content settings)
#
# Derived apps rearrange the content family to fit their own resources
# (e.g. editor / publisher / moderator). Do not create roles that span families.
ROLES: Sequence[tuple[int, str]] = (
    (1, "owner"),
    (2, "manager"),
    (3, "member"),
    (4, "guest"),
    (5, "system-admin"),
    (6, "user-admin"),
    (7, "auditor"),
    (8, "system-support"),
    (9, "content-admin"),
)

# --- Permission codes (scopes) ---------------------------------------------------
# Authorization uses scopes (permission code values). The code is the stable key; ids are assigned by the DB.
PERMISSION_CODES: Sequence[str] = (
    # --- Outside the tenants (SYSTEM_PERMISSIONS) ---
    # System settings (/api/admin/config). Viewing and changing are separate (ADR-0084 §3).
    "system-settings:view",
    "system-settings:write",
    # View system status (/api/admin/system/status).
    "system:view",
    # Restart, and grant/revoke people outside the tenants (operators, support staff).
    "system:manage",
    "log:view",
    # View the tenant list and status.
    "tenant:view",
    # Register/suspend/delete tenants and appoint the first tenant admin (ADR-0079 §1).
    "tenant:manage",
    # --- Inside a tenant ---
    # Content settings (the rules for that tenant's content; ADR-0084 §3).
    "content-settings:view",
    "content-settings:write",
    "user:manage",
    # Role definitions. Also used to read the permission code list in order to define roles (ADR-0084 §3).
    "role:manage",
    # Viewing audit logs (who did what). A separate scope from application logs (log:view),
    # because records that trace "who" need heavier handling than operational logs (ADR-0075 §1).
    "audit:view",
    "dashboard:view",
    "gui:view",
    "item:view",
    "item:write",
    # Shared notes (bounded_contexts/notes; the example for ADR-0078 §6). The scope only decides
    # "can use the feature". Which notes can be read or changed is decided in the DB by owner and group membership.
    "note:view",
    "note:write",
    # Create/edit groups (collections of users) and change membership (ADR-0081 §3).
    "group:manage",
    # Sending announcements from the admin screen. Can also read the group and user lists to pick recipients
    # (ADR-0081 §3).
    "notification:send",
)

# --- Outside the tenants (ADR-0079 §1) ---------------------------------------------
# Permissions that affect the whole app. Never give them to roles inside a tenant: otherwise
# one tenant's admin could change other tenants' settings or even restart the app.
SYSTEM_PERMISSIONS: Sequence[str] = (
    "system-settings:view",
    "system-settings:write",
    "system:view",
    "system:manage",
    "log:view",
    "tenant:view",
    "tenant:manage",
)

# Roles held only by users who belong to no tenant. They cannot be given to tenant users, and
# users outside the tenants cannot be given any other role (no combining).
SYSTEM_ROLES: Sequence[str] = ("system-admin", "system-support")

# The operator (system administrator) role. Used by the count that keeps at least one person able to
# manage tenants, and by the setup tool (scripts/create_system_admin.py).
SYSTEM_ADMIN_ROLE: str = "system-admin"

_TENANT_PERMISSIONS = tuple(code for code in PERMISSION_CODES if code not in SYSTEM_PERMISSIONS)

# --- Grants of permissions to roles ----------------------------------------------
# Role name -> set of granted permission codes. The effective scope is the union over the user's roles.
ROLE_PERMISSIONS: Mapping[str, Sequence[str]] = {
    "owner": _TENANT_PERMISSIONS,  # All permissions inside the tenant (tenant admin)
    # Editor. Creates, edits and deletes content.
    "manager": (
        "item:view",
        "item:write",
        "note:view",
        "note:write",
        "dashboard:view",
        "gui:view",
    ),
    "member": (
        "item:view",
        "note:view",
        "dashboard:view",
        "gui:view",
    ),
    "guest": (
        "dashboard:view",
        "gui:view",
    ),
    # Operator (outside the tenants). Touches neither content (item:*) nor the tenants' people
    # (user:* / role:*). Of the audit log, only records of global operations are visible (not tenant records).
    "system-admin": (
        *SYSTEM_PERMISSIONS,
        "audit:view",
        "dashboard:view",
        "gui:view",
    ),
    # Support staff (outside the tenants). Only views status to answer inquiries.
    # No settings, app logs or audit logs (they contain user information; ADR-0084 §2).
    "system-support": (
        "system:view",
        "tenant:view",
        "dashboard:view",
        "gui:view",
    ),
    # The people family. One can only hand out roles within one's own permissions (ADR-0078 §4),
    # so it has the same view permissions as member, allowing it to assign member and guest.
    # Raising someone to manager or owner is the job of those who hold them.
    "user-admin": (
        "user:manage",
        "group:manage",
        "item:view",
        "note:view",
        "dashboard:view",
        "gui:view",
    ),
    # Content admin. Changes the content rules and only reads the content itself. Give people who
    # also edit content manager as well (no roles spanning families; ADR-0078 §4).
    "content-admin": (
        "content-settings:view",
        "content-settings:write",
        "item:view",
        "note:view",
        "dashboard:view",
        "gui:view",
    ),
    # The audit family. Read only. Not a single permission to change anything (separation of duties).
    # App logs (log:view) cover the whole app, so they are not included (ADR-0079 §1).
    # Content is not readable either (what is checked is records and rules; ADR-0084 §2).
    "auditor": (
        "audit:view",
        "content-settings:view",
        "dashboard:view",
        "gui:view",
    ),
}

# --- Initial administrator ---------------------------------------------------------
# The password can be overridden with the ``ADMIN_INITIAL_PASSWORD`` environment variable
# (recommended). If unset, the fallback hash (plaintext = ``DEFAULT_ADMIN_PASSWORD``) is used,
# so in production always change it after the first sign-in.
#
# The Domain layer cannot depend on werkzeug (``tests/unit/test_layer_dependencies.py``), so a
# precomputed hash is stored here. ``tests/unit/test_master_data.py`` verifies it matches the
# plaintext.
DEFAULT_ADMIN_ID: int = 1
DEFAULT_ADMIN_EMAIL: str = "admin@example.com"
DEFAULT_ADMIN_USERNAME: str = "admin"
DEFAULT_ADMIN_ROLE: str = "owner"
DEFAULT_ADMIN_PASSWORD: str = "admin@example.com"
DEFAULT_ADMIN_PASSWORD_HASH: str = (
    "scrypt:32768:8:1$KdSu5I3W0KXRnlgp$"
    "ba3c41ed36121ffc856549df8ad55f1924ba78721ba417d1c8ab3eb6fc16d93cb28c4412"
    "692d00a5e7e32f9325936c35fbb5b8ed0dd2cb3a06230989706df370"
)

__all__ = [
    "DEFAULT_ADMIN_EMAIL",
    "DEFAULT_ADMIN_ID",
    "DEFAULT_ADMIN_PASSWORD",
    "DEFAULT_ADMIN_PASSWORD_HASH",
    "DEFAULT_ADMIN_ROLE",
    "DEFAULT_ADMIN_USERNAME",
    "PERMISSION_CODES",
    "ROLES",
    "ROLE_PERMISSIONS",
    "SYSTEM_ADMIN_ROLE",
    "SYSTEM_PERMISSIONS",
    "SYSTEM_ROLES",
]
