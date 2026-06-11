"""
RegistrationService — all business logic for creating registrations.
Views stay thin; all rules live here.
"""
import logging
from django.db import transaction as db_transaction, IntegrityError
from django.db.models import Count, Q
from django.utils import timezone

from apps.tickets.models import Ticket
from .models import Registration, RegistrationItem

logger = logging.getLogger(__name__)


class DuplicateEmailError(Exception):
    """Raised when an attendee email is blocked by ticket dedup rules."""
    def __init__(self, conflicts: dict):
        # conflicts = { ticket_name: [email1, email2] }
        self.conflicts = conflicts
        super().__init__(str(conflicts))

    def as_dict(self):
        return {
            'type': 'duplicate_email',
            'conflicts': self.conflicts,
        }


class TicketSoldOutError(Exception):
    """Raised when requested quantity exceeds available slots."""
    def __init__(self, ticket_name: str, available: int = 0):
        self.ticket_name = ticket_name
        self.available   = available
        super().__init__(f"'{ticket_name}' is sold out. Available: {available}")


class TicketNotAvailableError(Exception):
    """Raised when ticket is inactive or not found."""
    pass


def _check_email_duplicates(items: list[dict]) -> dict:
    """
    Event-wide duplicate email check.
    For each ticket:
      - If duplicate_email=False: block attendee emails already registered in ANY completed registration.
      - If duplicate_email=True: block attendee emails registered in a completed registration for a ticket type with duplicate_email=False.
    Also handles cross-ticket duplicate checks within the current transaction.
    Returns conflicts dict: { ticket_name: [blocked_emails] }
    """
    candidate_emails = set()
    for item in items:
        for att in item['attendees']:
            candidate_emails.add(att['email'].lower())

    # Bulk query completed registrations
    db_items = RegistrationItem.objects.filter(
        attendee_email__in=candidate_emails,
        registration__status='completed'
    ).select_related('ticket')

    emails_in_any_completed = set()
    emails_in_restricted_completed = set()

    for db_item in db_items:
        email = db_item.attendee_email.lower()
        emails_in_any_completed.add(email)
        if not db_item.ticket.duplicate_email:
            emails_in_restricted_completed.add(email)

    # Analyze current request for in-request duplicates
    from collections import defaultdict
    email_request_info = defaultdict(lambda: {'count': 0, 'has_restricted': False})
    for item in items:
        is_restricted = not item['ticket'].duplicate_email
        for att in item['attendees']:
            email = att['email'].lower()
            email_request_info[email]['count'] += 1
            if is_restricted:
                email_request_info[email]['has_restricted'] = True

    conflicts = {}
    for item in items:
        ticket: Ticket = item['ticket']
        blocked = []
        for att in item['attendees']:
            email = att['email'].lower()

            # 1. Check database completed registrations
            if not ticket.duplicate_email:
                if email in emails_in_any_completed:
                    blocked.append(email)
                    continue
            else:
                if email in emails_in_restricted_completed:
                    blocked.append(email)
                    continue

            # 2. Check current request items (in-request duplicates)
            if not ticket.duplicate_email:
                if email_request_info[email]['count'] > 1:
                    blocked.append(email)
                    continue
            else:
                if email_request_info[email]['has_restricted']:
                    blocked.append(email)
                    continue

        if blocked:
            conflicts[ticket.name] = list(set(blocked))

    return conflicts



def _check_quota(items: list[dict]) -> None:
    """
    Row-locked quota check. Must be called inside an atomic block.
    Extracts and sorts all ticket IDs in ascending order before acquiring locks.
    This deterministic lock order prevents database deadlocks.
    Raises TicketSoldOutError on first violation.
    """
    ticket_ids = sorted(list(set(item['ticket'].id for item in items)))
    locked_tickets = {
        t.id: t for t in Ticket.objects.select_for_update().filter(id__in=ticket_ids).order_by('id')
    }

    for item in items:
        ticket = locked_tickets[item['ticket'].id]

        if ticket.quantity_type == 'unlimited':
            continue

        now = timezone.now()
        active_payment_cutoff = now - timezone.timedelta(minutes=15)
        recent_pending_cutoff = now - timezone.timedelta(minutes=2)

        sold = RegistrationItem.objects.filter(
            ticket=ticket,
        ).filter(
            Q(registration__status='completed') |
            # Case 1: Pending registration with a transaction created within the payment window (15 mins)
            Q(
                registration__status='pending',
                registration__transaction__status='created',
                registration__created_at__gte=active_payment_cutoff
            ) |
            # Case 2: Pending registration created in the last 2 minutes, which is in the middle of creating its order/transaction
            Q(
                registration__status='pending',
                registration__transaction__isnull=True,
                registration__created_at__gte=recent_pending_cutoff
            )
        ).count()

        requested = len(item['attendees'])
        available = ticket.total_quantity - sold

        if requested > available:
            raise TicketSoldOutError(ticket.name, available)


@db_transaction.atomic
def create_registration(contact: dict, items: list[dict], user=None) -> Registration:
    """
    Main entry point. Validates, reserves, and persists a full registration.

    contact: { name, email, phone }
    items:   [ { ticket: Ticket, attendees: [{name, email, phone}] } ]
    user:    request.user or None (guest)
    """
    # 1. Validate all tickets are still active
    for item in items:
        ticket: Ticket = item['ticket']
        if not ticket.is_active:
            raise TicketNotAvailableError(
                f"'{ticket.name}' is no longer available."
            )

    # 2. Check duplicate emails BEFORE any writes (event-wide)
    conflicts = _check_email_duplicates(items)
    if conflicts:
        raise DuplicateEmailError(conflicts)

    # 3. Quota check with row lock (inside atomic — select_for_update requires this)
    _check_quota(items)

    # 4. Guard against double-submission:
    #    same contact email + pending status within last 15 seconds (prevents double-clicks)
    recent = Registration.objects.filter(
        contact_email=contact['email'].lower(),
        status='pending',
        created_at__gte=timezone.now() - timezone.timedelta(seconds=15)
    ).first()
    if recent:
        logger.warning(
            "Duplicate pending registration detected for %s, returning existing",
            contact['email']
        )
        return recent

    # 5. Create the Registration (billing contact)
    registration = Registration.objects.create(
        user=user,
        contact_name=contact['name'].strip(),
        contact_email=contact['email'].lower().strip(),
        contact_phone=contact['phone'].strip(),
    )

    # 6. Create RegistrationItems with inline attendee data
    for item in items:
        ticket: Ticket = item['ticket']
        for attendee_data in item['attendees']:
            RegistrationItem.objects.create(
                registration=registration,
                ticket=ticket,
                attendee_name=attendee_data['name'].strip(),
                attendee_email=attendee_data['email'].lower().strip(),
                attendee_phone=attendee_data.get('phone', '').strip(),
                unit_price=ticket.price,  # snapshot price at time of purchase
            )

    logger.info(
        "Registration REG-%04d created for %s (%s items)",
        registration.id, registration.contact_email,
        registration.items.count()
    )

    return registration


def expire_stale_pending_registrations_service() -> str:
    """
    Business service to expire pending registrations older than 15 minutes.
    Excludes registrations that have a pending/processing Transaction to prevent race conditions with in-flight payments.
    Triggers save signals and registers audit activities per registration.
    """
    from django.utils import timezone
    from apps.activity.utils import log_action

    cutoff = timezone.now() - timezone.timedelta(minutes=15)

    stale_regs = Registration.objects.filter(
        status='pending',
        created_at__lt=cutoff
    ).exclude(
        # Only protect registrations with an active Razorpay order still in play.
        # 'created' = order raised but user hasn't paid yet (could still complete).
        # 'paid'    = already captured — shouldn't be pending anyway, but guard it.
        # 'failed' / 'refunded' transactions should NOT block cleanup.
        transaction__status__in=['created', 'paid']
    )

    expired_ids = []
    for reg in stale_regs:
        reg.status = 'cancelled'
        reg.save(update_fields=['status'])
        expired_ids.append(reg.id)

        # Log audit action
        log_action(
            action='registration_expired',
            target=f"REG-{reg.id:04d}",
            metadata={'reason': 'Auto-cancelled due to inactivity (15-minute pending expiration)'}
        )

    if not expired_ids:
        return "No stale registrations found."

    return f"Expired {len(expired_ids)} stale registration(s): {expired_ids}"

