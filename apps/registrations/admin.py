from django.contrib import admin
from .models import Registration, RegistrationItem

class RegistrationItemInline(admin.TabularInline):
    model  = RegistrationItem
    extra  = 0
    fields = ['ticket', 'attendee_name', 'attendee_email', 'attendee_phone', 'unit_price']
    readonly_fields = ['unit_price']

@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display   = ['id', 'contact_name', 'contact_email', 'status', 'is_guest', 'total_amount', 'created_at']
    list_filter    = ['status']
    search_fields  = ['contact_email', 'contact_name']
    inlines        = [RegistrationItemInline]
    readonly_fields = ['created_at', 'updated_at', 'total_amount', 'is_guest']
