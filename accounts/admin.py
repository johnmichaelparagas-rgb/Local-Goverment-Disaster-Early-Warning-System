from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'name_display', 'role', 'municipality', 'is_active')
    list_filter = ('role', 'municipality', 'is_active')
    fieldsets = UserAdmin.fieldsets + (
        ('MDRRMO profile', {'fields': ('role', 'municipality')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('MDRRMO profile', {'fields': ('role', 'municipality')}),
    )

    @admin.display(description='Name')
    def name_display(self, obj):
        return obj.get_full_name() or obj.username
