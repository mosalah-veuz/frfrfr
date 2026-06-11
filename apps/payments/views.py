import json
import logging

from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

from apps.activity.utils import log_action
from apps.registrations.models import Registration
from .models import Transaction
from .services import confirm_payment, verify_webhook_signature, PaymentError

logger = logging.getLogger(__name__)


@require_POST
def payment_callback(request):
    """
    Called by Razorpay JS SDK after user completes payment on frontend.
    Verifies signature server-side before marking complete.
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request.'}, status=400)

    razorpay_order_id   = data.get('razorpay_order_id', '')
    razorpay_payment_id = data.get('razorpay_payment_id', '')
    razorpay_signature  = data.get('razorpay_signature', '')

    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        return JsonResponse({'error': 'Missing payment fields.'}, status=400)

    try:
        transaction = confirm_payment(razorpay_order_id, razorpay_payment_id, razorpay_signature)
    except PaymentError as exc:
        logger.warning("Payment confirmation failed: %s", exc)
        log_action(
            'payment_failed',
            target=razorpay_order_id,
            metadata={'reason': str(exc)},
            request=request,
        )
        return JsonResponse({'error': str(exc)}, status=400)

    user = request.user if request.user.is_authenticated else None
    log_action(
        'payment_verified',
        actor=user,
        target=f"REG-{transaction.registration_id:04d}",
        metadata={
            'order_id':   razorpay_order_id,
            'payment_id': razorpay_payment_id,
            'amount':     str(transaction.amount),
        },
        request=request,
    )

    return JsonResponse({
        'success':  True,
        'redirect': f'/confirm/{transaction.registration_id}/',
    })


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    """
    Razorpay server-to-server webhook.
    CSRF exempt — verified via HMAC signature instead.
    Always returns 200 to prevent Razorpay retries on non-critical errors.
    """
    sig = request.META.get('HTTP_X_RAZORPAY_SIGNATURE', '')

    if not verify_webhook_signature(request.body, sig):
        logger.warning("Webhook signature verification failed.")
        # Return 200 — don't reveal signature mismatch to caller
        return HttpResponse(status=200)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(status=200)

    event = payload.get('event', '')

    if event == 'payment.captured':
        payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
        order_id   = payment_entity.get('order_id', '')
        payment_id = payment_entity.get('id', '')

        try:
            transaction = Transaction.objects.get(razorpay_order_id=order_id)
        except Transaction.DoesNotExist:
            # Unknown order — acknowledge and ignore
            return HttpResponse(status=200)

        # Idempotent — confirm_payment handles already-processed case
        try:
            confirm_payment(order_id, payment_id, '')
            log_action(
                'payment_verified',
                target=f"REG-{transaction.registration_id:04d}",
                metadata={'source': 'webhook', 'event': event, 'order_id': order_id},
            )
        except PaymentError as exc:
            logger.error("Webhook payment confirm failed: %s", exc)

    elif event == 'payment.failed':
        payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
        order_id = payment_entity.get('order_id', '')
        try:
            transaction = Transaction.objects.get(razorpay_order_id=order_id)
            Transaction.objects.filter(id=transaction.id).update(status='failed')
            Registration.objects.filter(id=transaction.registration_id).update(status='failed')
            log_action(
                'payment_failed',
                target=f"REG-{transaction.registration_id:04d}",
                metadata={'source': 'webhook', 'order_id': order_id},
            )
        except Transaction.DoesNotExist:
            pass

    return HttpResponse(status=200)


@login_required
def payment_list(request):
    """Admin dashboard view displaying list of Razorpay transactions."""
    if not request.user.is_staff:
        return redirect('admin_login')

    from .selectors import get_transactions_selector
    from .filters import TransactionFilter

    qs = get_transactions_selector()
    f = TransactionFilter(request.GET, queryset=qs)
    transactions = f.qs

    return render(request, 'payments/list.html', {
        'filter':       f,
        'transactions': transactions,
    })
