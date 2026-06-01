from rest_framework import serializers

from .masking import coarse_coord
from .models import (
    HAZARD_STATUS_ORDER, HazardImage, HazardStatus, HazardType, Incident,
    MUNICIPALITIES, Reading, Sensor, Warning,
)


class HazardImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = HazardImage
        fields = ['id', 'incident', 'image', 'image_url', 'thumbnail_url',
                  'caption', 'uploaded_at']
        read_only_fields = ['thumbnail_url', 'uploaded_at']
        extra_kwargs = {'image': {'write_only': True, 'required': True}}

    def _abs(self, field):
        if not field:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(field.url) if request else field.url

    def get_image_url(self, obj):
        return self._abs(obj.image)

    def get_thumbnail_url(self, obj):
        return self._abs(obj.thumbnail) or self._abs(obj.image)


# ---------------------------------------------------------------------------
# Internal (secure dashboard) serializers — full operational detail.
# ---------------------------------------------------------------------------
class ReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reading
        fields = ['id', 'value', 'unit', 'recorded_at']


class SensorSerializer(serializers.ModelSerializer):
    last_reading = serializers.SerializerMethodField()

    class Meta:
        model = Sensor
        fields = [
            'id', 'device_id', 'name', 'hazard_type', 'municipality', 'barangay',
            'lat', 'lng', 'status', 'online', 'installed_at', 'updated_at', 'last_reading',
        ]
        read_only_fields = ['online', 'installed_at', 'updated_at']

    def get_last_reading(self, obj):
        r = obj.last_reading
        return ReadingSerializer(r).data if r else None


class IncidentSerializer(serializers.ModelSerializer):
    logged_by_name = serializers.CharField(source='logged_by.get_full_name', read_only=True, default='')
    images = HazardImageSerializer(many=True, read_only=True)

    class Meta:
        model = Incident
        fields = [
            'id', 'type', 'municipality', 'barangay', 'severity', 'status',
            'summary', 'public_summary',
            'dispatcher_name', 'dispatcher_phone', 'dispatcher_email',
            'reporter_name', 'reporter_contact',
            'internal_notes', 'lat', 'lng', 'reported_at', 'updated_at',
            'logged_by_name', 'images',
        ]
        read_only_fields = ['reported_at', 'updated_at', 'logged_by_name', 'images']

    def _is_privileged(self):
        """True when the request comes from an authenticated dispatcher/admin."""
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        return bool(user and user.is_authenticated and getattr(user, 'can_edit', False))

    def to_representation(self, instance):
        """Field-level masking: redact dispatcher contact info (and reporter
        PII / internal notes) for non-privileged (Public Viewer) requests."""
        data = super().to_representation(instance)
        if not self._is_privileged():
            for field in Incident.MASKED_CONTACT_FIELDS:
                if data.get(field):
                    data[field] = '[redacted]'
            # Public consumers also never see reporter PII / internal notes.
            for field in ('reporter_name', 'reporter_contact', 'internal_notes'):
                data.pop(field, None)
        return data


class WarningSerializer(serializers.ModelSerializer):
    issued_by_name = serializers.CharField(source='issued_by.get_full_name', read_only=True, default='')

    class Meta:
        model = Warning
        fields = [
            'id', 'title', 'level', 'hazard_type', 'message', 'municipalities',
            'effective_from', 'effective_until', 'issued_at', 'issuing_office',
            'active', 'cancelled_at', 'issued_by_name',
        ]
        read_only_fields = ['issued_at', 'active', 'cancelled_at', 'issued_by_name']

    def validate_municipalities(self, value):
        if not isinstance(value, list) or not value:
            raise serializers.ValidationError('Select at least one municipality.')
        invalid = [m for m in value if m not in MUNICIPALITIES]
        if invalid:
            raise serializers.ValidationError(f'Unknown municipalities: {", ".join(invalid)}.')
        return value


class BulkStatusSerializer(serializers.Serializer):
    """Validates a bulk hazard-status update request."""
    status = serializers.ChoiceField(choices=HazardStatus.choices)
    sensor_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list
    )
    municipality = serializers.ChoiceField(
        choices=[(m, m) for m in MUNICIPALITIES], required=False, allow_blank=True
    )
    hazard_type = serializers.ChoiceField(
        choices=HazardType.choices, required=False, allow_blank=True
    )

    def validate(self, attrs):
        if not attrs.get('sensor_ids') and not attrs.get('municipality') and not attrs.get('hazard_type'):
            raise serializers.ValidationError(
                'Provide sensor_ids and/or a municipality/hazard_type filter to target sensors.'
            )
        return attrs


# ---------------------------------------------------------------------------
# Public (masked) serializers — safe for mobile/citizen clients.
# ---------------------------------------------------------------------------
class PublicSensorSerializer(serializers.ModelSerializer):
    location = serializers.SerializerMethodField()
    last_reading = serializers.SerializerMethodField()

    class Meta:
        model = Sensor
        fields = ['id', 'name', 'hazard_type', 'municipality', 'barangay',
                  'status', 'location', 'last_reading', 'updated_at']

    def get_location(self, obj):
        return {'lat': coarse_coord(obj.lat), 'lng': coarse_coord(obj.lng)}

    def get_last_reading(self, obj):
        r = obj.last_reading
        if not r:
            return None
        return {'value': r.value, 'unit': r.unit, 'recorded_at': r.recorded_at}


class PublicIncidentSerializer(serializers.ModelSerializer):
    location = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()

    class Meta:
        model = Incident
        # No reporter PII, no internal notes.
        fields = ['id', 'type', 'municipality', 'barangay', 'status',
                  'severity', 'summary', 'location', 'reported_at']

    def get_location(self, obj):
        return {'lat': coarse_coord(obj.lat), 'lng': coarse_coord(obj.lng)}

    def get_summary(self, obj):
        return obj.public_summary or obj.summary


class PublicWarningSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warning
        # No issuer identity exposed.
        fields = ['id', 'title', 'level', 'hazard_type', 'message', 'municipalities',
                  'effective_from', 'effective_until', 'issued_at', 'issuing_office', 'active']
