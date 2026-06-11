from django.db.models import Sum
from django.utils import timezone
from apps.tickets.models import Ticket
from .models import RegistrationItem

def get_registration_items_selector():
    """
    Returns base queryset of registration items prefetching related tickets,
    parent registrations, and payment transactions.
    """
    return RegistrationItem.objects.select_related(
        'ticket',
        'registration',
        'registration__transaction',
    ).order_by('-registration__created_at')

def get_dashboard_stats_selector():
    """
    Returns aggregated metrics dictionary for the admin dashboard.
    """
    completed_items = RegistrationItem.objects.filter(registration__status='completed')
    total_rev = completed_items.aggregate(total=Sum('unit_price'))['total'] or 0
    cutoff = timezone.now() - timezone.timedelta(minutes=30)

    return {
        'total_tickets':       Ticket.objects.filter(is_active=True).count(),
        'total_registrations': completed_items.count(),
        'incomplete':          RegistrationItem.objects.filter(
            registration__status__in=['pending', 'processing'],
            registration__created_at__lte=cutoff
        ).count(),
        'total_revenue':       total_rev,
    }
