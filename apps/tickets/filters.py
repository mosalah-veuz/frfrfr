import django_filters
from .models import Ticket

class TicketFilter(django_filters.FilterSet):
    ticket_type   = django_filters.ChoiceFilter(
        choices=Ticket.TICKET_TYPE_CHOICES,
        empty_label='All ticket types',
        label='Ticket type',
    )
    quantity_type = django_filters.ChoiceFilter(
        choices=Ticket.QUANTITY_TYPE_CHOICES,
        empty_label='All quantity types',
        label='Quantity type',
    )
    is_active     = django_filters.ChoiceFilter(
        choices=[(True, 'Active'), (False, 'Inactive')],
        empty_label='All statuses',
        label='Active status',
    )

    class Meta:
        model  = Ticket
        fields = ['ticket_type', 'quantity_type', 'is_active']
