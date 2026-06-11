from celery import shared_task

@shared_task(name="registrations.expire_stale_pending_registrations")
def expire_stale_pending_registrations():
    """
    Celery shared task to expire registrations in pending status older than 15 minutes.
    Delegates task execution to registrations service layer.
    """
    from .services import expire_stale_pending_registrations_service
    return expire_stale_pending_registrations_service()
