from .models import Transaction

def get_transactions_selector():
    """
    Returns optimized queryset of transactions, prefetching related registrations.
    """
    return Transaction.objects.select_related(
        'registration'
    ).order_by('-created_at')
