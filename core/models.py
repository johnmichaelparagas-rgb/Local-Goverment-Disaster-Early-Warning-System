from django.conf import settings
from django.db import models
from django.utils import timezone


# A representative set of Leyte (province) municipalities + nearby cities.
MUNICIPALITIES = [
    'Tacloban City', 'Palo', 'Tanauan', 'Tolosa', 'Dulag', 'Abuyog',
    'Baybay City', 'Ormoc City', 'Carigara', 'Barugo', 'Jaro', 'Pastrana',
    'Alangalang', 'Santa Fe', 'Tabontabon', 'MacArthur',
]
MUNICIPALITY_CHOICES = [(m, m) for m in MUNICIPALITIES]


class HazardStatus(models.TextChoices):
    NORMAL = 'normal', 'Normal'
    ADVISORY = 'advisory', 'Advisory'
    WATCH = 'watch', 'Watch'
    WARNING = 'warning', 'Warning'
    CRITICAL = 'critical', 'Critical'


# Severity ladder used for sorting / "highest status" rollups.
HAZARD_STATUS_ORDER = [s.value for s in HazardStatus]


class HazardType(models.TextChoices):
    FLOOD = 'flood', 'Flood'
    RAINFALL = 'rainfall', 'Rainfall'
    RIVER_LEVEL = 'river_level', 'River level'
    LANDSLIDE = 'landslide', 'Landslide'
    STORM_SURGE = 'storm_surge', 'Storm surge'
    SEISMIC = 'seismic', 'Seismic'


class Sensor(models.Model):
    device_id = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    hazard_type = models.CharField(max_length=20, choices=HazardType.choices)
    municipality = models.CharField(max_length=120, choices=MUNICIPALITY_CHOICES)
    barangay = models.CharField(max_length=120, blank=True)
    # Precise device coordinates — masked before exposure to the public API.
    lat = models.FloatField()
    lng = models.FloatField()
    status = models.CharField(
        max_length=20, choices=HazardStatus.choices, default=HazardStatus.NORMAL
    )
    online = models.BooleanField(default=True)
    installed_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['municipality', 'name']

    @property
    def last_reading(self):
        return self.readings.order_by('-recorded_at').first()

    def __str__(self):
        return f'{self.name} [{self.municipality}]'


class Reading(models.Model):
    sensor = models.ForeignKey(Sensor, related_name='readings', on_delete=models.CASCADE)
    value = models.FloatField()
    unit = models.CharField(max_length=16, blank=True)
    recorded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-recorded_at']

    def __str__(self):
        return f'{self.sensor.name}: {self.value} {self.unit}'


class Incident(models.Model):
    class Type(models.TextChoices):
        FLOODING = 'flooding', 'Flooding'
        LANDSLIDE = 'landslide', 'Landslide'
        ROAD_BLOCKAGE = 'road_blockage', 'Road blockage'
        STRUCTURAL = 'structural_damage', 'Structural damage'
        CASUALTY = 'casualty', 'Casualty'
        EVACUATION = 'evacuation', 'Evacuation'
        POWER_OUTAGE = 'power_outage', 'Power outage'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        REPORTED = 'reported', 'Reported'
        IN_PROGRESS = 'in_progress', 'In Progress'
        RESOLVED = 'resolved', 'Resolved'
        CLOSED = 'closed', 'Closed'

    class Severity(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'

    type = models.CharField(max_length=24, choices=Type.choices)
    municipality = models.CharField(max_length=120, choices=MUNICIPALITY_CHOICES)
    barangay = models.CharField(max_length=120, blank=True)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.MEDIUM)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REPORTED)
    summary = models.TextField(help_text='Internal summary for LGU staff.')
    public_summary = models.TextField(
        blank=True, help_text='Sanitized text shown on the public feed.'
    )

    # Dispatcher / responder contact details. These are MASKED in API output
    # for unauthenticated (Public Viewer) requests and only revealed to
    # authenticated dispatchers/admins.
    dispatcher_name = models.CharField(max_length=120, blank=True)
    dispatcher_phone = models.CharField(max_length=40, blank=True)
    dispatcher_email = models.EmailField(blank=True)

    # Reporter PII — never exposed by the public API.
    reporter_name = models.CharField(max_length=120, blank=True)
    reporter_contact = models.CharField(max_length=40, blank=True)
    internal_notes = models.TextField(blank=True)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    reported_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    logged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='incidents',
    )

    # Incidents shown publicly only once an LGU has acted on them.
    PUBLIC_STATUSES = {Status.IN_PROGRESS, Status.RESOLVED, Status.CLOSED}

    # Contact fields masked from public (unauthenticated) consumers.
    MASKED_CONTACT_FIELDS = ('dispatcher_name', 'dispatcher_phone', 'dispatcher_email')

    class Meta:
        ordering = ['-reported_at']

    def __str__(self):
        return f'{self.get_type_display()} @ {self.municipality}'


def hazard_image_path(instance, filename):
    return f'hazard_images/incident_{instance.incident_id or "new"}/{filename}'


class HazardImage(models.Model):
    """A photo attached to an incident (one incident -> many images)."""
    incident = models.ForeignKey(
        Incident, related_name='images', on_delete=models.CASCADE
    )
    image = models.ImageField(upload_to=hazard_image_path)
    thumbnail = models.ImageField(upload_to='hazard_images/thumbs/', blank=True, null=True)
    caption = models.CharField(max_length=200, blank=True)
    uploaded_at = models.DateTimeField(default=timezone.now)

    THUMBNAIL_SIZE = (300, 300)

    class Meta:
        ordering = ['uploaded_at']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.image and not self.thumbnail:
            self._build_thumbnail()

    def _build_thumbnail(self):
        """Generate a thumbnail with Pillow and store it alongside the image."""
        import io
        from pathlib import Path
        from PIL import Image
        from django.core.files.base import ContentFile

        try:
            self.image.open()
            img = Image.open(self.image)
            img = img.convert('RGB')
            img.thumbnail(self.THUMBNAIL_SIZE)
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=80)
            name = f'thumb_{Path(self.image.name).stem}.jpg'
            self.thumbnail.save(name, ContentFile(buffer.getvalue()), save=False)
            super().save(update_fields=['thumbnail'])
        except Exception:
            # A bad/corrupt upload should never block saving the incident.
            pass

    def __str__(self):
        return f'Image for incident #{self.incident_id}'


class Warning(models.Model):
    class Level(models.TextChoices):
        INFORMATION = 'information', 'Information'
        YELLOW = 'yellow', 'Yellow'
        ORANGE = 'orange', 'Orange'
        RED = 'red', 'Red'

    title = models.CharField(max_length=160)
    level = models.CharField(max_length=12, choices=Level.choices)
    hazard_type = models.CharField(max_length=20, choices=HazardType.choices)
    message = models.TextField()
    # Stored as a JSON list of municipality names.
    municipalities = models.JSONField(default=list)
    effective_from = models.DateTimeField(default=timezone.now)
    effective_until = models.DateTimeField(null=True, blank=True)
    issued_at = models.DateTimeField(default=timezone.now)
    issuing_office = models.CharField(max_length=80, default='MDRRMO')
    active = models.BooleanField(default=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='warnings',
    )

    class Meta:
        ordering = ['-issued_at']

    def __str__(self):
        return f'[{self.level}] {self.title}'


class AuditLog(models.Model):
    """Accountability trail for sensitive LGU actions."""
    at = models.DateTimeField(default=timezone.now)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='audit_entries'
    )
    actor_name = models.CharField(max_length=120, blank=True)
    action = models.CharField(max_length=80)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-at']

    def __str__(self):
        return f'{self.at:%Y-%m-%d %H:%M} {self.action}'
