from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db.models import ProtectedError
from django import forms
import django_filters

from apps.activity.utils import log_action
from .models import Ticket
from .forms import TicketForm


from .filters import TicketFilter
from .selectors import get_all_tickets_with_counts_selector


def _render_ticket_list(request, form_by_ticket_id=None, edit_ticket_id=None):
    qs = get_all_tickets_with_counts_selector()
    f = TicketFilter(request.GET, queryset=qs)
    tickets = list(f.qs)
    form_by_ticket_id = form_by_ticket_id or {}
    for ticket in tickets:
        ticket.edit_form = form_by_ticket_id.get(ticket.pk) or TicketForm(instance=ticket)

    return render(request, 'tickets/list.html', {
        'filter': f,
        'tickets': tickets,
        'edit_ticket_id': edit_ticket_id,
    })


@login_required
def ticket_list(request):
    if not request.user.is_staff:
        return redirect('admin_login')

    return _render_ticket_list(request)


@login_required
def ticket_create(request):
    if not request.user.is_staff:
        return redirect('admin_login')

    form = TicketForm()
    if request.method == 'POST':
        form = TicketForm(request.POST)
        if form.is_valid():
            ticket = form.save()
            log_action(
                'ticket_create',
                actor=request.user,
                target=f"Ticket #{ticket.id} — {ticket.name}",
                metadata={
                    'ticket_type':   ticket.ticket_type,
                    'price':         str(ticket.price),
                    'quantity_type': ticket.quantity_type,
                    'total_quantity': ticket.total_quantity,
                },
                request=request
            )
            messages.success(request, f"Ticket '{ticket.name}' created successfully.")
            return redirect('ticket_list')

    return render(request, 'tickets/form.html', {'form': form, 'action': 'Create'})


@login_required
def ticket_update(request, pk):
    if not request.user.is_staff:
        return redirect('admin_login')

    ticket = get_object_or_404(Ticket, pk=pk)
    if request.method == 'POST':
        form = TicketForm(request.POST, instance=ticket)
        if form.is_valid():
            ticket = form.save()
            log_action(
                'ticket_update',
                actor=request.user,
                target=f"Ticket #{ticket.id} — {ticket.name}",
                metadata={
                    'ticket_type':   ticket.ticket_type,
                    'price':         str(ticket.price),
                    'quantity_type': ticket.quantity_type,
                    'total_quantity': ticket.total_quantity,
                },
                request=request
            )
            messages.success(request, f"Ticket '{ticket.name}' updated successfully.")
            return redirect('ticket_list')
        return _render_ticket_list(
            request,
            form_by_ticket_id={ticket.pk: form},
            edit_ticket_id=ticket.pk,
        )

    return redirect('ticket_list')


@login_required
@require_POST
def ticket_activate(request, pk):
    if not request.user.is_staff:
        return redirect('admin_login')

    ticket = get_object_or_404(Ticket, pk=pk)
    ticket.is_active = True
    ticket.save(update_fields=['is_active'])
    messages.success(request, f"Ticket '{ticket.name}' activated.")
    return redirect('ticket_list')


@login_required
@require_POST
def ticket_delete(request, pk):
    if not request.user.is_staff:
        return redirect('admin_login')

    ticket = get_object_or_404(Ticket, pk=pk)
    name   = ticket.name

    # Soft delete when any registration rows reference this ticket.
    if ticket.registration_items.exists():
        # Soft delete only — can't remove ticket with completed registrations
        ticket.is_active = False
        ticket.save(update_fields=['is_active'])
        messages.warning(
            request,
            f"'{name}' has completed registrations — it has been deactivated instead of deleted."
        )
    else:
        try:
            ticket.delete()
            log_action(
                'ticket_delete',
                actor=request.user,
                target=f"Ticket #{ticket.id} — {name}",
                metadata={'ticket_name': name},
                request=request
            )
            messages.success(request, f"Ticket '{name}' deleted.")
        except ProtectedError:
            messages.error(request, f"Cannot delete '{name}' — it has pending registrations.")

    return redirect('ticket_list')
