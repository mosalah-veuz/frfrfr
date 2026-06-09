"""
RegistrationService — all business logic for creating registrations.
Views stay thin; all rules live here.
"""
import logging
from django.db import transaction as db_transaction, IntegrityError
from django.db.models import Count
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
    For each ticket where duplicate_email=False, check if ANY attendee email
    already exists in ANY completed registration across the entire event.
    Returns conflicts dict: { ticket_name: [blocked_emails] }
    """
    conflicts = {}
    for item in items:
        ticket: Ticket = item['ticket']
        if ticket.duplicate_email:
            continue  # this ticket allows email reuse

        attendee_emails = [a['email'].lower() for a in item['attendees']]

        # Check against ALL completed registration items (event-wide)
        blocked = list(
            RegistrationItem.objects.filter(
                attendee_email__in=attendee_emails,
                registration__status='completed'
            ).values_list('attendee_email', flat=True).distinct()
        )

        if blocked:
            conflicts[ticket.name] = blocked

    return conflicts


def _check_quota(items: list[dict]) -> None:
    """
    Row-locked quota check. Must be called inside an atomic block.
    Raises TicketSoldOutError on first violation.
    """
    for item in items:
        ticket: Ticket = Ticket.objects.select_for_update().get(id=item['ticket'].id)

        if ticket.quantity_type == 'unlimited':
            continue

        sold = RegistrationItem.objects.filter(
            ticket=ticket,
            registration__status__in=['processing', 'completed']
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
    #    same contact email + pending status within last 5 minutes
    recent = Registration.objects.filter(
        contact_email=contact['email'].lower(),
        status='pending',
        created_at__gte=timezone.now() - timezone.timedelta(minutes=5)
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
