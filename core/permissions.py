from rest_framework import permissions


class IsEditorOrReadOnly(permissions.BasePermission):
    """Authenticated viewers get read-only access; admin/dispatcher can write."""
    message = 'Insufficient permissions for this action.'

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, 'can_edit', False)
        )


class IsLGUAdmin(permissions.BasePermission):
    """Only LGU Admins (full CRUD + user management)."""
    message = 'This action requires LGU Admin privileges.'

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, 'is_lgu_admin', False)
        )


class IncidentPermission(permissions.BasePermission):
    """Incident access rules matching the three LGU roles:

      - Public Viewer (unauthenticated or 'viewer'): read-only.
      - Dispatcher: read + update existing incidents (status/notes), but cannot
        create or delete incidents.
      - LGU Admin: full CRUD.
    """
    message = 'Insufficient permissions for this action.'

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if getattr(user, 'is_lgu_admin', False):
            return True
        # Dispatchers may update but not create or delete.
        if getattr(user, 'is_dispatcher', False):
            return request.method in ('PUT', 'PATCH')
        return False
