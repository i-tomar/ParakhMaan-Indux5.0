"""Role-based access control. Enforced on the API; the frontend only mirrors it for navigation."""

OPERATOR = "OPERATOR"
QUALITY_MANAGER = "QUALITY_MANAGER"
ADMIN = "ADMIN"
AUDITOR = "AUDITOR"
ROLES = (OPERATOR, QUALITY_MANAGER, ADMIN, AUDITOR)

# Roles used before the Operator / Quality Manager model
LEGACY_ROLE_MAP = {"INSPECTOR": OPERATOR, "SUPERVISOR": QUALITY_MANAGER}

PERMISSIONS: dict[str, set[str]] = {
    "inspection:read": {OPERATOR, QUALITY_MANAGER, ADMIN, AUDITOR},
    "inspection:write": {OPERATOR, QUALITY_MANAGER, ADMIN},
    "review:write": {OPERATOR, QUALITY_MANAGER, ADMIN},
    "inspection:finalize": {QUALITY_MANAGER, ADMIN},
    "analytics:read": {QUALITY_MANAGER, ADMIN, AUDITOR},
    "org:read": {OPERATOR, QUALITY_MANAGER, ADMIN, AUDITOR},
    "org:manage": {ADMIN},
    "user:manage": {ADMIN},
    "system:configure": {ADMIN},
    # Learning loop: managers curate datasets, train, run shadow tests and approve models;
    # only administrators may promote a model that did not pass the evaluation gate.
    "model:read": {QUALITY_MANAGER, ADMIN, AUDITOR},
    "model:manage": {QUALITY_MANAGER, ADMIN},
    "model:override": {ADMIN},
}


def normalize_role(role: str | None) -> str:
    role = (role or OPERATOR).upper()
    return LEGACY_ROLE_MAP.get(role, role)


def has_permission(role: str | None, permission: str) -> bool:
    return normalize_role(role) in PERMISSIONS.get(permission, set())


def permissions_for(role: str | None) -> list[str]:
    r = normalize_role(role)
    return sorted(p for p, roles in PERMISSIONS.items() if r in roles)
