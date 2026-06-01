from django.contrib import admin

from .models import AuditLog, Incident, Reading, Sensor, Warning


class ReadingInline(admin.TabularInline):
    model = Reading
    extra = 0
    readonly_fields = ('recorded_at',)


@admin.register(Sensor)
class SensorAdmin(admin.ModelAdmin):
    list_display = ('name', 'hazard_type', 'municipality', 'status', 'online', 'updated_at')
    list_filter = ('hazard_type', 'status', 'municipality', 'online')
    search_fields = ('name', 'device_id', 'barangay')
    inlines = [ReadingInline]


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ('type', 'municipality', 'severity', 'status', 'reported_at')
    list_filter = ('type', 'severity', 'status', 'municipality')
    search_fields = ('summary', 'barangay', 'reporter_name')


@admin.register(Warning)
class WarningAdmin(admin.ModelAdmin):
    list_display = ('title', 'level', 'hazard_type', 'active', 'issued_at')
    list_filter = ('level', 'hazard_type', 'active')
    search_fields = ('title', 'message')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('at', 'actor_name', 'action')
    list_filter = ('action',)
    readonly_fields = ('at', 'actor', 'actor_name', 'action', 'details')

    def has_add_permission(self, request):
        return False
