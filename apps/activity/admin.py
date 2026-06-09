from django.contrib import admin
from .models import ActivityLog

@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display  = ['timestamp', 'actor', 'action', 'target', 'ip_address']
    list_filter   = ['action']
    search_fields = ['actor__username', 'target']
    readonly_fields = ['timestamp', 'actor', 'action', 'target', 'metadata', 'ip_address']

    def has_add_permission(self, request):
        return False  # logs are append-only

    def has_change_permission(self, request, obj=None):
        return False  # immutable

    def has_delete_permission(self, request, obj=None):
        return False
