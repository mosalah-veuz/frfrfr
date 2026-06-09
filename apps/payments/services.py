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

    # Move registration to processing
    Registration.objects.filter(id=registration.id).update(status='processing')

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

    # Verify signature
    if not verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
        logger.warning("Signature mismatch for order %s", razorpay_order_id)
        _mark_failed(transaction)
        raise PaymentError("Payment signature verification failed.")

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
    return transaction


def _mark_failed(transaction: Transaction):
    Transaction.objects.filter(id=transaction.id).update(status='failed')
    Registration.objects.filter(id=transaction.registration_id).update(status='failed')


def verify_webhook_signature(payload_body: bytes, received_sig: str) -> bool:
    """Verify Razorpay webhook signature using webhook secret."""
    expected = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, received_sig)
