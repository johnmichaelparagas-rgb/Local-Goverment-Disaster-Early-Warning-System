"""Create the three LGU role Groups and assign model permissions.

Idempotent — safe to run any time (e.g. after deploy/migrate):

    python manage.py setup_roles
"""
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from accounts.models import User
from core.models import HazardImage, Incident, Sensor, Warning


def perms_for(model, actions):
    ct = ContentType.objects.get_for_model(model)
    codenames = [f'{a}_{model._meta.model_name}' for a in actions]
    return list(Permission.objects.filter(content_type=ct, codename__in=codenames))


class Command(BaseCommand):
    help = 'Create LGU role groups (LGU Admin, Dispatcher, Public Viewer) and assign permissions.'

    def handle(self, *args, **options):
        ALL = ['add', 'change', 'delete', 'view']

        # LGU Admin — full CRUD on domain models + user management.
        admin_perms = []
        for model in (Incident, HazardImage, Sensor, Warning):
            admin_perms += perms_for(model, ALL)
        admin_perms += perms_for(User, ALL)  # user management

        # Dispatcher — view everything, update incidents/images/sensors/warnings,
        # but no create/delete of incidents and no user management.
        dispatcher_perms = []
        dispatcher_perms += perms_for(Incident, ['view', 'change'])
        dispatcher_perms += perms_for(HazardImage, ['view', 'add', 'change'])
        dispatcher_perms += perms_for(Sensor, ['view', 'change'])
        dispatcher_perms += perms_for(Warning, ['view', 'add', 'change'])

        # Public Viewer — read-only.
        viewer_perms = []
        for model in (Incident, HazardImage, Sensor, Warning):
            viewer_perms += perms_for(model, ['view'])

        matrix = {
            'LGU Admin': admin_perms,
            'Dispatcher': dispatcher_perms,
            'Public Viewer': viewer_perms,
        }
        for name, perms in matrix.items():
            group, _ = Group.objects.get_or_create(name=name)
            group.permissions.set(perms)
            self.stdout.write(self.style.SUCCESS(f'  {name}: {len(perms)} permissions set'))

        # Re-sync every user's group membership to their role.
        synced = 0
        for user in User.objects.all():
            user.sync_group()
            synced += 1
        self.stdout.write(self.style.SUCCESS(f'Synced group membership for {synced} user(s).'))
