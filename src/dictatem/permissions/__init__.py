"""macOS first-run permission guidance (pure half).

See ``docs/adr/0014`` for the decision: the daemon detects missing TCC
grants natively and shows a guided dialog; the *mapping* from missing
permissions to System Settings panes and copy is pure and unit-tested.
"""

from dictatem.permissions.mapper import (
    MacPermission,
    PermissionGuidance,
    map_missing_permissions,
)

__all__ = ["MacPermission", "PermissionGuidance", "map_missing_permissions"]
