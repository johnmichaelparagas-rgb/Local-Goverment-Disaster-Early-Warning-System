from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .filters import IncidentFilter
from .models import (
    AuditLog, HAZARD_STATUS_ORDER, HazardImage, Incident, Reading, Sensor, Warning,
)
from .permissions import IncidentPermission, IsEditorOrReadOnly
from .serializers import (
    BulkStatusSerializer, HazardImageSerializer, IncidentSerializer,
    PublicIncidentSerializer, PublicSensorSerializer, PublicWarningSerializer,
    ReadingSerializer, SensorSerializer, WarningSerializer,
)


def record_audit(request, action_name, **details):
    user = request.user if request.user.is_authenticated else None
    AuditLog.objects.create(
        actor=user,
        actor_name=(user.get_full_name() or user.username) if user else 'system',
        action=action_name,
        details=details,
    )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
class LoginView(APIView):
    """Exchange username/password for a JWT access token + user profile."""
    permission_classes = [AllowAny]
    # No session auth here: this endpoint is token-based, so it must not run
    # SessionAuthentication (which would enforce CSRF when a Django session
    # cookie is present — e.g. after signing into the /login/ management UI).
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        from django.contrib.auth import authenticate

        username = (request.data.get('username') or '').strip()
        password = request.data.get('password') or ''
        try:
            user = authenticate(request, username=username, password=password)
        except PermissionDenied:
            # Raised by django-axes when the account/IP is locked out.
            return Response(
                {'error': 'Account temporarily locked after too many failed attempts. '
                          'Try again later.', 'locked': True},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if not user or not user.is_active:
            return Response({'error': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

        refresh = RefreshToken.for_user(user)
        AuditLog.objects.create(
            actor=user, actor_name=user.get_full_name() or user.username,
            action='auth.login', details={'username': username},
        )
        return Response({
            'token': str(refresh.access_token),
            'refresh': str(refresh),
            'user': _user_payload(user),
        })


class MeView(APIView):
    def get(self, request):
        return Response({'user': _user_payload(request.user)})


def _user_payload(user):
    return {
        'id': user.id,
        'username': user.username,
        'name': user.get_full_name() or user.username,
        'role': user.role,
        'role_label': user.get_role_display(),
        'municipality': user.municipality,
        'can_edit': user.can_edit,
        'can_manage_users': user.can_manage_users,
    }


# ---------------------------------------------------------------------------
# Secure dashboard API (auth required)
# ---------------------------------------------------------------------------
class SensorViewSet(viewsets.ModelViewSet):
    queryset = Sensor.objects.all()
    serializer_class = SensorSerializer
    permission_classes = [IsEditorOrReadOnly]

    def get_queryset(self):
        qs = Sensor.objects.all()
        params = self.request.query_params
        if params.get('municipality'):
            qs = qs.filter(municipality=params['municipality'])
        if params.get('hazard_type'):
            qs = qs.filter(hazard_type=params['hazard_type'])
        if params.get('status'):
            qs = qs.filter(status=params['status'])
        return qs

    def perform_create(self, serializer):
        sensor = serializer.save()
        record_audit(self.request, 'sensor.create', sensor_id=sensor.id, name=sensor.name)

    @action(detail=True, methods=['post'])
    def readings(self, request, pk=None):
        """Ingest a reading from a field device; optionally set status."""
        sensor = self.get_object()
        value = request.data.get('value')
        if value is None:
            return Response({'error': 'A numeric "value" is required.'}, status=400)
        try:
            value = float(value)
        except (TypeError, ValueError):
            return Response({'error': '"value" must be numeric.'}, status=400)
        unit = request.data.get('unit') or (sensor.last_reading.unit if sensor.last_reading else '')
        reading = Reading.objects.create(sensor=sensor, value=value, unit=unit)
        new_status = request.data.get('status')
        if new_status and new_status in dict(Sensor._meta.get_field('status').choices):
            sensor.status = new_status
        sensor.online = True
        sensor.save(update_fields=['status', 'online', 'updated_at'])
        return Response(
            {'reading': ReadingSerializer(reading).data, 'sensor': SensorSerializer(sensor).data},
            status=201,
        )

    @action(detail=False, methods=['patch'], url_path='bulk-status')
    def bulk_status(self, request):
        """Raise/lower hazard status across many sensors in one operation."""
        serializer = BulkStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        qs = Sensor.objects.all()
        if data.get('sensor_ids'):
            qs = qs.filter(id__in=data['sensor_ids'])
        if data.get('municipality'):
            qs = qs.filter(municipality=data['municipality'])
        if data.get('hazard_type'):
            qs = qs.filter(hazard_type=data['hazard_type'])

        matched = list(qs)
        if not matched:
            return Response({'error': 'No sensors matched the given targets.'}, status=404)

        new_status = data['status']
        now = timezone.now()
        changes = []
        to_update = []
        for s in matched:
            if s.status != new_status:
                changes.append({'id': s.id, 'name': s.name, 'from': s.status, 'to': new_status})
                s.status = new_status
                s.updated_at = now
                to_update.append(s)
        if to_update:
            Sensor.objects.bulk_update(to_update, ['status', 'updated_at'])

        record_audit(
            request, 'sensor.bulk_status', status=new_status,
            matched=len(matched), changed=len(changes),
            filter={'municipality': data.get('municipality'),
                    'hazard_type': data.get('hazard_type'),
                    'ids_count': len(data.get('sensor_ids') or [])},
        )
        return Response({
            'status': new_status,
            'matched': len(matched),
            'updated': len(changes),
            'changes': changes,
        })


class IncidentViewSet(viewsets.ModelViewSet):
    """Incidents API.

    - Reads are open (Public Viewer): the serializer masks dispatcher contact
      info and strips reporter PII for non-privileged requests.
    - Dispatchers may update existing incidents; only LGU Admins may create or
      delete. Enforced by IncidentPermission.
    """
    queryset = Incident.objects.all().prefetch_related('images')
    serializer_class = IncidentSerializer
    permission_classes = [IncidentPermission]
    filterset_class = IncidentFilter

    def perform_create(self, serializer):
        incident = serializer.save(logged_by=self.request.user)
        record_audit(self.request, 'incident.create',
                     incident_id=incident.id, type=incident.type, municipality=incident.municipality)

    def perform_update(self, serializer):
        incident = serializer.save()
        record_audit(self.request, 'incident.update', incident_id=incident.id, status=incident.status)

    def perform_destroy(self, instance):
        record_audit(self.request, 'incident.delete', incident_id=instance.id)
        instance.delete()


class HazardImageViewSet(viewsets.ModelViewSet):
    """Hazard images attached to incidents (one incident -> many images)."""
    queryset = HazardImage.objects.select_related('incident').all()
    serializer_class = HazardImageSerializer
    permission_classes = [IsEditorOrReadOnly]
    parser_classes = [MultiPartParser, FormParser]
    filterset_fields = ['incident']

    def perform_create(self, serializer):
        image = serializer.save()
        record_audit(self.request, 'hazard_image.create',
                     image_id=image.id, incident_id=image.incident_id)


class WarningViewSet(viewsets.ModelViewSet):
    queryset = Warning.objects.all()
    serializer_class = WarningSerializer
    permission_classes = [IsEditorOrReadOnly]
    http_method_names = ['get', 'post', 'head', 'options']  # cancel via custom action

    def get_queryset(self):
        qs = Warning.objects.all()
        if self.request.query_params.get('active') == 'true':
            qs = qs.filter(active=True)
        return qs

    def perform_create(self, serializer):
        warning = serializer.save(issued_by=self.request.user)
        record_audit(self.request, 'warning.broadcast',
                     warning_id=warning.id, level=warning.level, municipalities=warning.municipalities)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        warning = self.get_object()
        warning.active = False
        warning.cancelled_at = timezone.now()
        warning.save(update_fields=['active', 'cancelled_at'])
        record_audit(request, 'warning.cancel', warning_id=warning.id)
        return Response(WarningSerializer(warning).data)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@api_view(['GET'])
@permission_classes([AllowAny])
def health(request):
    return Response({
        'status': 'ok',
        'service': 'leyte-dews-portal',
        'time': timezone.now(),
        'counts': {
            'sensors': Sensor.objects.count(),
            'incidents': Incident.objects.count(),
            'warnings': Warning.objects.count(),
            'active_warnings': Warning.objects.filter(active=True).count(),
        },
    })


# ---------------------------------------------------------------------------
# Public masked API (mobile / citizen clients)
# ---------------------------------------------------------------------------
class PublicApiKeyMixin:
    """Optional X-API-Key gate, plus open throttling for public clients."""
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'public'

    def check_api_key(self, request):
        keys = settings.PUBLIC_API_KEYS
        if not keys:
            return True
        provided = request.headers.get('X-API-Key') or request.query_params.get('api_key')
        return provided in keys

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not self.check_api_key(request):
            from rest_framework.exceptions import AuthenticationFailed
            raise AuthenticationFailed('A valid X-API-Key is required.')


class PublicSensorsView(PublicApiKeyMixin, APIView):
    def get(self, request):
        qs = Sensor.objects.all()
        if request.query_params.get('municipality'):
            qs = qs.filter(municipality=request.query_params['municipality'])
        return Response({
            'updated_at': timezone.now(),
            'sensors': PublicSensorSerializer(qs, many=True).data,
        })


class PublicWarningsView(PublicApiKeyMixin, APIView):
    def get(self, request):
        qs = Warning.objects.filter(active=True)
        muni = request.query_params.get('municipality')
        warnings = [w for w in qs if not muni or muni in w.municipalities]
        return Response({
            'updated_at': timezone.now(),
            'warnings': PublicWarningSerializer(warnings, many=True).data,
        })


class PublicIncidentsView(PublicApiKeyMixin, APIView):
    def get(self, request):
        qs = Incident.objects.filter(status__in=[s.value for s in Incident.PUBLIC_STATUSES])
        if request.query_params.get('municipality'):
            qs = qs.filter(municipality=request.query_params['municipality'])
        return Response({
            'updated_at': timezone.now(),
            'incidents': PublicIncidentSerializer(qs, many=True).data,
        })


class PublicSituationView(PublicApiKeyMixin, APIView):
    """One-shot snapshot for a municipality — ideal for mobile home screens."""
    def get(self, request):
        muni = request.query_params.get('municipality')
        sensors = Sensor.objects.all()
        if muni:
            sensors = sensors.filter(municipality=muni)
        warnings = [
            w for w in Warning.objects.filter(active=True)
            if not muni or muni in w.municipalities
        ]
        incidents = Incident.objects.filter(status__in=[s.value for s in Incident.PUBLIC_STATUSES])
        if muni:
            incidents = incidents.filter(municipality=muni)

        highest = 'normal'
        for s in sensors:
            if HAZARD_STATUS_ORDER.index(s.status) > HAZARD_STATUS_ORDER.index(highest):
                highest = s.status

        return Response({
            'municipality': muni or 'All Leyte',
            'updated_at': timezone.now(),
            'overall_hazard_status': highest,
            'active_warnings': len(warnings),
            'sensors': PublicSensorSerializer(sensors, many=True).data,
            'warnings': PublicWarningSerializer(warnings, many=True).data,
            'incidents': PublicIncidentSerializer(incidents, many=True).data,
        })
