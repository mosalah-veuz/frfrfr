from django.db.models import Count, Q, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from .models import Ticket

def get_active_tickets_with_counts_selector():
    """
    Returns active tickets annotated with sold_count to prevent N+1 query loops.
    """
    now = timezone.now()
    active_payment_cutoff = now - timezone.timedelta(minutes=15)
    recent_pending_cutoff = now - timezone.timedelta(minutes=2)

    sold_count_filter = Q(
        registration_items__registration__status='completed'
    ) | Q(
        registration_items__registration__status='pending',
        registration_items__registration__transaction__status='created',
        registration_items__registration__created_at__gte=active_payment_cutoff
    ) | Q(
        registration_items__registration__status='pending',
        registration_items__registration__transaction__isnull=True,
        registration_items__registration__created_at__gte=recent_pending_cutoff
    )
    return Ticket.objects.filter(is_active=True).annotate(
        annotated_sold_count=Coalesce(
            Count('registration_items', filter=sold_count_filter),
            Value(0)
        )
    ).order_by('ticket_type', 'price')

def get_all_tickets_with_counts_selector():
    """
    Returns all tickets annotated with sold_count for the admin management view.
    """
    now = timezone.now()
    active_payment_cutoff = now - timezone.timedelta(minutes=15)
    recent_pending_cutoff = now - timezone.timedelta(minutes=2)

    sold_count_filter = Q(
        registration_items__registration__status='completed'
    ) | Q(
        registration_items__registration__status='pending',
        registration_items__registration__transaction__status='created',
        registration_items__registration__created_at__gte=active_payment_cutoff
    ) | Q(
        registration_items__registration__status='pending',
        registration_items__registration__transaction__isnull=True,
        registration_items__registration__created_at__gte=recent_pending_cutoff
    )
    return Ticket.objects.annotate(
        annotated_sold_count=Coalesce(
            Count('registration_items', filter=sold_count_filter),
            Value(0)
        )
    ).order_by('-created_at')
