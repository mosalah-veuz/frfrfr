"""
PaymentService — Razorpay integration.
All Razorpay calls go through here. Views never touch the SDK directly.
"""
import hmac
import hashlib
import logging

import razorpay
from django.conf import settings
from django.utils import timezone
from django.db import transaction as db_transaction

from apps.registrations.models import Registration
from .models import Transaction

logger = logging.getLogger(__name__)

client = razorpay.Client(
    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
)


class PaymentError(Exception):
    pass


def create_order(registration: Registration) -> Transaction:
    """
    Create a Razorpay order and persist a Transaction record.
    Amount is calculated fresh from DB — never trust the frontend.
    """
    # Recalculate total server-side
    total = sum(item.unit_price for item in registration.items.all())

    if total <= 0:
        raise PaymentError("Cannot create payment order for zero-amount registration.")

    amount_paise = int(total * 100)  # Razorpay expects paise (integer)

    try:
        order = client.order.create({
            'amount':   amount_paise,
            'currency': 'INR',
            'receipt':  f'reg_{registration.id}',
            'notes': {
                'registration_id': registration.id,
                'contact_email':   registration.contact_email,
            }
        })
    except Exception as exc:
        logger.error("Razorpay order creation failed for REG-%04d: %s", registration.id, exc)
        raise PaymentError(f"Payment gateway error: {exc}") from exc

    transaction = Transaction.objects.create(
        registration=registration,
        razorpay_order_id=order['id'],
        amount=total,
        status='created',
    )

    # Registration stays 'pending' — it only moves to 'completed' on confirmed payment
    # or gets cleaned up by the stale-transaction sweep if the user closes the modal.

    logger.info(
        "Razorpay order %s created for REG-%04d (₹%s)",
        order['id'], registration.id, total
    )
    return transaction


def verify_payment_signature(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str
) -> bool:
    """
    HMAC-SHA256 verification. Never trust the frontend payment success.
    """
    message = f"{razorpay_order_id}|{razorpay_payment_id}"
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, razorpay_signature)


@db_transaction.atomic
def confirm_payment(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str
) -> Transaction:
    """
    Called after successful Razorpay callback.
    Idempotent — safe to call multiple times for the same order.
    """
    try:
        transaction = Transaction.objects.select_for_update().get(
            razorpay_order_id=razorpay_order_id
        )
    except Transaction.DoesNotExist:
        logger.warning("Unknown Razorpay order: %s", razorpay_order_id)
        raise PaymentError(f"Order {razorpay_order_id} not found.")

    # Already processed — idempotent, just return
    if transaction.status == 'paid':
        logger.info("Order %s already processed — skipping.", razorpay_order_id)
        return transaction

    # Verify signature if provided (e.g. frontend callback).
    # Webhooks pass empty signature because the webhook's request signature is already verified.
    if razorpay_signature:
        if not verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
            logger.warning("Signature mismatch for order %s", razorpay_order_id)
            _mark_failed(transaction)
            raise PaymentError("Payment signature verification failed.")

    # --- Fallback Quota Verification Guard (Concurrency Safety) ---
    registration = transaction.registration
    items = list(registration.items.select_related('ticket').all())
    ticket_ids = sorted(list(set(item.ticket_id for item in items)))

    from apps.tickets.models import Ticket
    from apps.registrations.models import RegistrationItem

    # Lock tickets deterministically to prevent deadlocks
    locked_tickets = {
        t.id: t for t in Ticket.objects.select_for_update().filter(id__in=ticket_ids).order_by('id')
    }

    oversold_tickets = []
    for item in items:
        ticket = locked_tickets[item.ticket_id]
        if ticket.quantity_type == 'unlimited':
            continue

        # Count all OTHER completed registrations for this ticket (excluding our registration)
        other_completed = RegistrationItem.objects.filter(
            ticket=ticket,
            registration__status='completed'
        ).exclude(registration=registration).count()

        requested = sum(1 for ri in items if ri.ticket_id == ticket.id)
        available = ticket.total_quantity - other_completed

        if requested > available:
            oversold_tickets.append(ticket.name)

    if oversold_tickets:
        logger.warning(
            "Oversell detected during confirmation for REG-%04d on tickets: %s. Initiating refund for payment %s.",
            registration.id, oversold_tickets, razorpay_payment_id
        )
        _refund_and_fail(transaction, razorpay_payment_id)
        raise PaymentError(f"Tickets {', '.join(oversold_tickets)} are sold out. Refund initiated.")

    # Update transaction
    Transaction.objects.filter(id=transaction.id).update(
        razorpay_payment_id=razorpay_payment_id,
        razorpay_signature=razorpay_signature,
        status='paid',
        verified_at=timezone.now(),
    )

    # Update registration
    Registration.objects.filter(id=transaction.registration_id).update(
        status='completed'
    )

    transaction.refresh_from_db()
    logger.info(
        "Payment verified: order=%s payment=%s REG-%04d",
        razorpay_order_id, razorpay_payment_id, transaction.registration_id
    )

    # Fetch full payment details from Razorpay and persist them.
    # Wrapped in try/except — a gateway hiccup must never roll back a confirmed payment.
    if razorpay_payment_id:
        try:
            payment_entity = client.payment.fetch(razorpay_payment_id)
            _save_payment_details(transaction.id, payment_entity)
        except Exception as exc:
            logger.warning(
                "Could not fetch payment details for %s: %s",
                razorpay_payment_id, exc
            )

    return transaction


def _mark_failed(transaction: Transaction):
    Transaction.objects.filter(id=transaction.id).update(status='failed')
    Registration.objects.filter(id=transaction.registration_id).update(status='failed')


def _refund_and_fail(transaction: Transaction, payment_id: str):
    """
    Refunds a captured payment via Razorpay, marks transaction as 'failed',
    and registration as 'failed'. Logs activity event.
    """
    Transaction.objects.filter(id=transaction.id).update(status='failed')
    Registration.objects.filter(id=transaction.registration_id).update(status='failed')

    from apps.activity.utils import log_action
    log_action(
        'payment_failed',
        target=f"REG-{transaction.registration_id:04d}",
        metadata={'reason': 'Ticket sold out (concurrency fallback refund initiated)'}
    )

    if payment_id:
        try:
            amount_paise = int(transaction.amount * 100)
            refund = client.payment.refund(payment_id, {
                'amount': amount_paise,
                'speed': 'optimum',
                'notes': {
                    'reason': 'Automated refund due to ticket oversell / sold out',
                    'registration_id': transaction.registration_id,
                }
            })
            logger.info("Razorpay refund initiated successfully: %s", refund.get('id', 'N/A'))
        except Exception as exc:
            logger.exception("Failed to trigger Razorpay refund for payment %s: %s", payment_id, exc)


def _save_payment_details(transaction_id: int, payment_entity: dict) -> None:
    """
    Map a Razorpay payment entity dict onto the Transaction model fields.
    Called after a payment is captured — either from the JS callback or a webhook.
    All fields are optional so a partial entity never corrupts the row.
    """
    method = payment_entity.get('method', '') or ''
    card   = payment_entity.get('card') or {}

    fee_paise = payment_entity.get('fee') or 0
    tax_paise = payment_entity.get('tax') or 0

    Transaction.objects.filter(id=transaction_id).update(
        payment_method  = method,
        # Card details
        card_network    = card.get('network', '') or '',
        card_issuer     = card.get('issuer', '') or '',
        card_last4      = card.get('last4', '') or '',
        card_type       = card.get('type', '') or '',
        card_name       = card.get('name', '') or '',
        # Method-specific
        bank            = payment_entity.get('bank', '') or '',
        wallet          = payment_entity.get('wallet', '') or '',
        vpa             = payment_entity.get('vpa', '') or '',
        # Fees (Razorpay sends amounts in paise — convert to ₹)
        razorpay_fee    = round(fee_paise / 100, 2) if fee_paise else None,
        razorpay_tax    = round(tax_paise / 100, 2) if tax_paise else None,
        # Error details (blank for successful payments)
        error_code          = payment_entity.get('error_code', '') or '',
        error_description   = payment_entity.get('error_description', '') or '',
    )
    logger.info("Payment details saved for TXN-%s: method=%s", transaction_id, method)


def verify_webhook_signature(payload_body: bytes, received_sig: str) -> bool:
    """Verify Razorpay webhook signature using webhook secret."""
    expected = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, received_sig)
