"""
Logging utility. Import log_action anywhere in the codebase.
"""
from .models import ActivityLog


def log_action(action: str, actor=None, target: str = '', metadata: dict = None, request=None):
    """
    Create an ActivityLog entry.
    ip_address is extracted from request if provided.
    """
    ip = None
    if request:
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = x_forwarded.split(',')[0].strip() if x_forwarded else request.META.get('REMOTE_ADDR')

    ActivityLog.objects.create(
        actor=actor if (actor and actor.is_authenticated) else None,
        action=action,
        target=target,
        metadata=metadata or {},
        ip_address=ip,
    )
