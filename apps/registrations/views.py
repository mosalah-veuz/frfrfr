import json
import logging

from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.utils import timezone
from django import forms

from apps.activity.utils import log_action
from apps.tickets.models import Ticket
from apps.tickets.selectors import get_active_tickets_with_counts_selector
from .models import Registration, RegistrationItem
from .forms import ContactForm, AttendeeForm, RegistrationItemForm
from .filters import RegistrationFilter
from .selectors import get_registration_items_selector
from .services import (
    create_registration,
    DuplicateEmailError,
    TicketSoldOutError,
    TicketNotAvailableError,
)

logger = logging.getLogger(__name__)


# ─── Public Portal ───────────────────────────────────────────────

def portal(request):
    """Public ticket listing page."""
    tickets = get_active_tickets_with_counts_selector()
    return render(request, 'registrations/portal.html', {
        'tickets': tickets,
    })


def attendee_details(request):
    """Page where users input attendee details for their selected tickets."""
    initial = {}
    if request.user.is_authenticated:
        initial = {
            'first_name': request.user.first_name,
            'last_name':  request.user.last_name,
            'email':      request.user.email,
        }
    return render(request, 'registrations/attendees.html', {
        'initial': initial,
    })


def checkout(request):
    """Public checkout page where user confirms tickets and enters contact info to register."""
    tickets = get_active_tickets_with_counts_selector()
    initial = {}
    if request.user.is_authenticated:
        phone = ''
        try:
            if hasattr(request.user, 'profile'):
                phone = request.user.profile.phone
        except Exception:
            pass
        initial = {
            'first_name': request.user.first_name,
            'last_name':  request.user.last_name,
            'email':      request.user.email,
            'phone':      phone,
        }
    return render(request, 'registrations/checkout.html', {
        'tickets': tickets,
        'initial': initial,
    })


@require_POST
def register(request):
    """AJAX endpoint — validates and creates a registration."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request.'}, status=400)

    dry_run = data.get('dry_run', False)

    # --- Validate items ---
    raw_items = data.get('items', [])
    if not raw_items:
        return JsonResponse({'errors': {'items': 'Select at least one ticket.'}}, status=400)

    validated_items = []
    item_errors     = {}

    for idx, raw_item in enumerate(raw_items):
        # Validate ticket
        item_form = RegistrationItemForm({'ticket_id': raw_item.get('ticket_id')})
        if not item_form.is_valid():
            item_errors[idx] = item_form.errors
            continue

        ticket = item_form.cleaned_data['ticket_id']

        # Validate attendees
        raw_attendees = raw_item.get('attendees', [])
        if not raw_attendees:
            item_errors[idx] = {'attendees': 'At least one attendee required.'}
            continue

        attendee_forms   = [AttendeeForm(a) for a in raw_attendees]
        invalid_attendees = {}
        for i, f in enumerate(attendee_forms):
            if not f.is_valid():
                invalid_attendees[i] = {field: msgs[0] for field, msgs in f.errors.items()}

        if invalid_attendees:
            item_errors[idx] = {'attendees': invalid_attendees}
            continue

        # Check for duplicate emails within the same item submission (local duplicates)
        if not ticket.duplicate_email:
            emails = [f.cleaned_data['email'].lower() for f in attendee_forms]
            seen_emails = set()
            local_duplicates = {}
            for i, email in enumerate(emails):
                if email in seen_emails:
                    local_duplicates[i] = {'email': f"Duplicate email address '{email}' in this ticket group."}
                seen_emails.add(email)

            if local_duplicates:
                item_errors[idx] = {'attendees': local_duplicates}
                continue

        attendees_data = []
        for f in attendee_forms:
            data_dict = f.cleaned_data.copy()
            data_dict['name'] = f"{data_dict['first_name']} {data_dict['last_name']}".strip()
            attendees_data.append(data_dict)

        validated_items.append({
            'ticket':    ticket,
            'attendees': attendees_data,
        })

    if item_errors:
        return JsonResponse({'errors': {'items': item_errors}}, status=400)

    # Determine if registration is free
    is_free = all(item['ticket'].price == 0 for item in validated_items)

    # --- Validate contact (only if not dry run) ---
    if not dry_run:
        raw_contact = data.get('contact', {})
        if is_free:
            # Default missing fields to the first attendee's details
            if not raw_contact.get('first_name') or not raw_contact.get('email'):
                first_att = validated_items[0]['attendees'][0]
                name_parts = first_att['name'].split(' ', 1)
                first_name = name_parts[0]
                last_name = name_parts[1] if len(name_parts) > 1 else ''
                raw_contact = {
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': first_att['email'],
                    'phone': first_att.get('phone', '') or '+910000000000',
                }
            elif not raw_contact.get('phone'):
                raw_contact['phone'] = '+910000000000'

        contact_form = ContactForm(raw_contact)
        if is_free:
            contact_form.fields['phone'].required = False

        if not contact_form.is_valid():
            return JsonResponse({'errors': {'contact': contact_form.errors}}, status=400)

    # --- Business constraints check (even for dry run) ---
    # 1. Event-wide duplicate email check
    try:
        from .services import _check_email_duplicates, DuplicateEmailError
        conflicts = _check_email_duplicates(validated_items)
        if conflicts:
            for idx, item in enumerate(validated_items):
                t_name = item['ticket'].name
                if t_name in conflicts:
                    blocked_list = [e.lower() for e in conflicts[t_name]]
                    row_errors = {}
                    for i, att in enumerate(item['attendees']):
                        if att['email'].lower() in blocked_list:
                            if item['ticket'].duplicate_email:
                                # This ticket allows duplicates, but the email is blocked
                                # because it was registered under a restricted ticket type.
                                row_errors[i] = {'email': "This email is already registered for a ticket that does not allow duplicate registrations."}
                            else:
                                # This ticket itself does not allow duplicates,
                                # and the email already appears in a completed registration anywhere on the event.
                                row_errors[i] = {'email': "This email address has already been registered for this event and cannot be used again."}
                    if row_errors:
                        item_errors[idx] = {'attendees': row_errors}
            if item_errors:
                return JsonResponse({'errors': {'items': item_errors}}, status=400)
    except Exception as exc:
        logger.exception("Error checking email duplicates: %s", exc)

    # 2. Quota check
    for idx, item in enumerate(validated_items):
        ticket = item['ticket']
        if ticket.quantity_type == 'unlimited':
            continue
        requested = len(item['attendees'])
        available = ticket.available_count
        if requested > available:
            return JsonResponse({'errors': {'global': f"'{ticket.name}' is sold out. Available slots left: {available}."}}, status=400)


    if dry_run:
        return JsonResponse({'success': True, 'valid': True})

    # --- Service call ---
    user = request.user if request.user.is_authenticated else None
    try:
        contact_data = contact_form.cleaned_data.copy()
        contact_data['name'] = f"{contact_data['first_name']} {contact_data['last_name']}".strip()
        registration = create_registration(
            contact=contact_data,
            items=validated_items,
            user=user,
        )
    except DuplicateEmailError as exc:
        return JsonResponse({'errors': exc.as_dict()}, status=400)
    except TicketSoldOutError as exc:
        return JsonResponse({'errors': {'sold_out': str(exc)}}, status=400)
    except TicketNotAvailableError as exc:
        return JsonResponse({'errors': {'unavailable': str(exc)}}, status=400)
    except Exception as exc:
        logger.exception("Unexpected error during registration: %s", exc)
        return JsonResponse({'errors': {'server': 'An unexpected error occurred. Please try again.'}}, status=500)

    # --- Route: paid vs free ---
    total = registration.total_amount

    if total > 0:
        from apps.payments.services import create_order, PaymentError
        from django.conf import settings
        try:
            transaction = create_order(registration)
        except PaymentError as exc:
            return JsonResponse({'errors': {'payment': str(exc)}}, status=500)

        log_action(
            'payment_created',
            actor=user,
            target=f"REG-{registration.id:04d}",
            metadata={'order_id': transaction.razorpay_order_id, 'amount': str(total)},
            request=request,
        )

        return JsonResponse({
            'success':  True,
            'payment':  True,
            'order_id': transaction.razorpay_order_id,
            'amount':   int(total * 100),
            'key_id':   settings.RAZORPAY_KEY_ID,
            'reg_id':   registration.id,
            'name':     registration.contact_name,
            'email':    registration.contact_email,
            'phone':    registration.contact_phone,
        })

    # Free registration — mark completed immediately
    Registration.objects.filter(id=registration.id).update(status='completed')
    return JsonResponse({
        'success':  True,
        'payment':  False,
        'redirect': f'/confirm/{registration.id}/',
    })


def confirmation(request, pk):
    registration = get_object_or_404(
        Registration.objects.prefetch_related('items__ticket'),
        pk=pk, status='completed'
    )
    return render(request, 'registrations/confirmation.html', {'registration': registration})


# ─── Admin views ─────────────────────────────────────────────────


@login_required
def registration_list(request):
    if not request.user.is_staff:
        return redirect('admin_login')

    qs = get_registration_items_selector()

    f = RegistrationFilter(request.GET, queryset=qs)

    # Incomplete = stale pending/processing older than 30 min
    cutoff     = timezone.now() - timezone.timedelta(minutes=30)
    completed  = f.qs.filter(registration__status='completed')
    incomplete = f.qs.filter(
        registration__status__in=['pending', 'processing'],
        registration__created_at__lte=cutoff
    )
    all_regs   = f.qs

    return render(request, 'registrations/list.html', {
        'filter':     f,
        'completed':  completed,
        'incomplete': incomplete,
        'all_regs':   all_regs,
    })
