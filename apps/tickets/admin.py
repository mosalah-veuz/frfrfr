from django.contrib import admin
from .models import Ticket
from .forms import TicketForm

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    form = TicketForm
    list_display  = ['name', 'ticket_type', 'price', 'quantity_type', 'total_quantity', 'is_active', 'sold_count']
    list_filter   = ['ticket_type', 'quantity_type', 'is_active']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at', 'sold_count']
