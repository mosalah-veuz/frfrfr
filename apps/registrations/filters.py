import django_filters
from django import forms
from django.db.models import Q

from apps.tickets.models import Ticket
from .models import Registration, RegistrationItem

class RegistrationFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(
        choices=Registration.STATUS_CHOICES,
        field_name='registration__status',
        empty_label='All statuses',
        label='Status',
    )
    search = django_filters.CharFilter(
        method='filter_search',
        label='Search attendee/contact',
        widget=forms.TextInput(attrs={'placeholder': 'Search name, email, phone…'}),
    )
    ticket = django_filters.ModelChoiceFilter(
        queryset=Ticket.objects.filter(is_active=True),
        field_name='ticket',
        empty_label='All ticket types',
        label='Ticket type',
    )
    date_from = django_filters.DateFilter(
        field_name='registration__created_at',
        lookup_expr='date__gte',
        label='From date',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    date_to = django_filters.DateFilter(
        field_name='registration__created_at',
        lookup_expr='date__lte',
        label='To date',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    class Meta:
        model  = RegistrationItem
        fields = ['status', 'search', 'ticket', 'date_from', 'date_to']

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(attendee_name__icontains=value) |
            Q(attendee_email__icontains=value) |
            Q(attendee_phone__icontains=value) |
            Q(registration__contact_name__icontains=value) |
            Q(registration__contact_email__icontains=value)
        )
