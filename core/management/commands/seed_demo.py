"""Seed the portal with demo LGU accounts, sensors, incidents, and a warning.

    python manage.py seed_demo            # seed only if empty
    python manage.py seed_demo --force    # wipe domain data and reseed
"""
import io
import random
from datetime import timedelta

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User
from core.models import HazardImage, Incident, Reading, Sensor, Warning


DEMO_USERS = [
    ('admin', 'Admin@2024', 'Maria Santos', User.Role.ADMIN, 'Tacloban City'),
    ('dispatcher', 'Dispatcher@2024', 'Juan Dela Cruz', User.Role.DISPATCHER, 'Palo'),
    ('viewer', 'Viewer@2024', 'Ana Reyes', User.Role.VIEWER, 'Tanauan'),
]


def make_sample_image(label, color):
    """Generate a small labelled JPEG in memory (so the seed needs no assets)."""
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (640, 480), color)
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), label, fill='white')
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=85)
    return ContentFile(buf.getvalue(), name=f'{label.lower().replace(" ", "_")}.jpg')

SENSORS = [
    ('Mantorlot River Gauge', 'river_level', 'Tacloban City', 'Brgy. 109', 11.2447, 125.0048, 'm', 2.1, 'advisory'),
    ('San Juanico Tide Station', 'storm_surge', 'Tacloban City', 'Brgy. 70 Naga-Naga', 11.3286, 124.9711, 'm', 0.8, 'normal'),
    ('Palo Rain Gauge', 'rainfall', 'Palo', 'Brgy. San Joaquin', 11.1575, 124.9908, 'mm/hr', 14.5, 'watch'),
    ('Binahaan River Sensor', 'flood', 'Pastrana', 'Brgy. Cabaohan', 11.1239, 124.8889, 'm', 3.4, 'warning'),
    ('Tanauan Coastal Buoy', 'storm_surge', 'Tanauan', 'Brgy. Bislig', 11.1108, 125.0211, 'm', 1.2, 'advisory'),
    ('Abuyog Slope Monitor', 'landslide', 'Abuyog', 'Brgy. Can-aporong', 10.7469, 125.0117, 'deg', 3.1, 'normal'),
    ('Ormoc Pagsangaan Gauge', 'river_level', 'Ormoc City', 'Brgy. Cogon', 11.0064, 124.6075, 'm', 2.7, 'watch'),
    ('Leyte Seismic Node', 'seismic', 'Carigara', 'Brgy. Poblacion', 11.2978, 124.6817, 'PGA', 0.02, 'normal'),
]

# type, muni, brgy, severity, status, summary, reporter, contact,
# dispatcher_name, dispatcher_phone, dispatcher_email
INCIDENTS = [
    ('flooding', 'Pastrana', 'Brgy. Cabaohan', 'high', 'in_progress',
     'Knee-deep floodwater on access road; 12 families pre-emptively evacuated.',
     'Pedro Mabini', '+639171234567',
     'Disp. Rosa Lim', '+639170001111', 'rlim@pastrana.mdrrmo.gov.ph'),
    ('landslide', 'Abuyog', 'Brgy. Can-aporong', 'medium', 'in_progress',
     'Soil slip blocking one lane of the mountain road.',
     'Lita Gomez', '+639281112233',
     'Disp. Mark Yu', '+639170002222', 'myu@abuyog.mdrrmo.gov.ph'),
    ('power_outage', 'Palo', 'Brgy. San Joaquin', 'low', 'reported',
     'Brownout affecting two sitios after heavy rain.',
     'Anonymous', '', '', '', ''),
    ('road_blockage', 'Ormoc City', 'Brgy. Cogon', 'medium', 'resolved',
     'Fallen tree cleared by barangay response team.',
     'Brgy. Tanod J. Ramos', '+639395556677',
     'Disp. Ben Tan', '+639170003333', 'btan@ormoc.mdrrmo.gov.ph'),
]


class Command(BaseCommand):
    help = 'Seed demo data for the Leyte DEWS portal.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Wipe domain data and reseed.')

    def handle(self, *args, **options):
        force = options['force']
        if User.objects.filter(is_superuser=False).exists() and not force:
            self.stdout.write(self.style.WARNING(
                'Data already present. Use --force to wipe and reseed.'))
            return

        if force:
            HazardImage.objects.all().delete()
            Reading.objects.all().delete()
            Sensor.objects.all().delete()
            Incident.objects.all().delete()
            Warning.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()

        now = timezone.now()

        # Accounts
        admin_user = None
        for username, pw, full, role, muni in DEMO_USERS:
            first, _, last = full.partition(' ')
            user = User.objects.create_user(
                username=username, password=pw, first_name=first, last_name=last,
                role=role, municipality=muni,
            )
            if role == User.Role.ADMIN:
                admin_user = user
                user.is_staff = True  # allow Django admin access
                user.save(update_fields=['is_staff'])

        # Sensors + readings
        for name, htype, muni, brgy, lat, lng, unit, val, st in SENSORS:
            sensor = Sensor.objects.create(
                device_id=f'LEY-{htype[:3].upper()}-{random.randint(1000, 9999)}',
                name=name, hazard_type=htype, municipality=muni, barangay=brgy,
                lat=lat, lng=lng, status=st,
                installed_at=now - timedelta(days=200),
            )
            for i in range(6):
                Reading.objects.create(
                    sensor=sensor,
                    value=round(val + random.uniform(-0.5, 0.5), 2),
                    unit=unit,
                    recorded_at=now - timedelta(minutes=30 * (i + 1)),
                )
            # Most-recent reading reflects the headline value.
            Reading.objects.create(sensor=sensor, value=val, unit=unit,
                                   recorded_at=now - timedelta(minutes=random.randint(1, 20)))

        # Incidents (+ sample hazard images on the first one)
        first_incident = None
        for row in INCIDENTS:
            (itype, muni, brgy, sev, st, summary, reporter, contact,
             disp_name, disp_phone, disp_email) = row
            incident = Incident.objects.create(
                type=itype, municipality=muni, barangay=brgy, severity=sev, status=st,
                summary=summary, public_summary=summary,
                reporter_name=reporter, reporter_contact=contact,
                dispatcher_name=disp_name, dispatcher_phone=disp_phone, dispatcher_email=disp_email,
                logged_by=admin_user,
                reported_at=now - timedelta(minutes=random.randint(20, 300)),
            )
            first_incident = first_incident or incident

        # Attach a couple of generated images to demonstrate thumbnails.
        for label, color in [('Flooded Road', (37, 99, 235)), ('Evacuation Site', (5, 150, 105))]:
            HazardImage.objects.create(
                incident=first_incident,
                image=make_sample_image(label, color),
                caption=label,
            )

        # Active early warning
        Warning.objects.create(
            title='Orange Rainfall Warning — Central Leyte',
            level='orange', hazard_type='rainfall',
            message=('Heavy rains expected within 2 hours. Residents in low-lying and '
                     'riverside barangays of Palo, Pastrana, and Tanauan should prepare to '
                     'evacuate. Monitor official LGU channels.'),
            municipalities=['Palo', 'Pastrana', 'Tanauan'],
            effective_from=now - timedelta(minutes=30),
            effective_until=now + timedelta(hours=3),
            issuing_office='PDRRMO Leyte', issued_by=admin_user,
        )

        # Create role Groups + permissions and sync membership.
        call_command('setup_roles')

        self.stdout.write(self.style.SUCCESS('Seed complete.'))
        self.stdout.write('  admin      / Admin@2024       (LGU Admin, Django admin access)')
        self.stdout.write('  dispatcher / Dispatcher@2024  (Dispatcher)')
        self.stdout.write('  viewer     / Viewer@2024      (Public Viewer)')
