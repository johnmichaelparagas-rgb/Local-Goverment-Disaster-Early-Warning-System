from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """LGU staff account for the MDRRMO portal.

    Roles (also mirrored as Django Groups for permission management):
      admin      - "LGU Admin": full CRUD on incidents/images + user management
      dispatcher - view + update incident status / monitoring; no user management
      viewer     - "Public Viewer": read-only access to public-safe data
    """

    class Role(models.TextChoices):
        ADMIN = 'admin', 'LGU Admin'
        DISPATCHER = 'dispatcher', 'Dispatcher'
        VIEWER = 'viewer', 'Public Viewer'

    # Django Group names that correspond to each role.
    GROUP_NAMES = {
        Role.ADMIN: 'LGU Admin',
        Role.DISPATCHER: 'Dispatcher',
        Role.VIEWER: 'Public Viewer',
    }

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VIEWER)
    municipality = models.CharField(max_length=120, blank=True)

    @property
    def is_lgu_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_dispatcher(self):
        return self.role == self.Role.DISPATCHER

    @property
    def can_edit(self):
        """Admins and dispatchers may perform write operations."""
        return self.role in (self.Role.ADMIN, self.Role.DISPATCHER)

    @property
    def can_manage_users(self):
        return self.role == self.Role.ADMIN

    def sync_group(self):
        """Ensure the user's Group membership matches their role."""
        from django.contrib.auth.models import Group
        target = self.GROUP_NAMES.get(self.role)
        self.groups.clear()
        if target:
            group, _ = Group.objects.get_or_create(name=target)
            self.groups.add(group)

    def __str__(self):
        return f'{self.username} ({self.role})'
