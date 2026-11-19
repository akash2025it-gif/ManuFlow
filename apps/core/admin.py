from django.contrib import admin
from .models import AuditLogEntry


@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    list_display = (
        'timestamp',
        'user_email',
        'user_role',
        'module',
        'action',
        'object_repr',
        'reference_number',
        'ip_address',
    )
    list_filter = ('module', 'action', 'user_role', 'timestamp')
    search_fields = ('object_repr', 'object_id', 'reference_number', 'user_email', 'details')
    ordering = ('-timestamp',)
    readonly_fields = [f.name for f in AuditLogEntry._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
