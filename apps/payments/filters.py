import django_filters
from django import forms
from django.db.models import Q
from .models import Transaction

class TransactionFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(
        choices=Transaction.STATUS_CHOICES,
        empty_label='All statuses',
        label='Status',
    )
    search = django_filters.CharFilter(
        method='filter_search',
        label='Search ID/Contact',
        widget=forms.TextInput(attrs={'placeholder': 'Search Order ID, Payment ID, Name, Email…'}),
    )
    date_from = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='date__gte',
        label='From date',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    date_to = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='date__lte',
        label='To date',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    class Meta:
        model = Transaction
        fields = ['status', 'search', 'date_from', 'date_to']

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        value = value.strip()
        return queryset.filter(
            Q(razorpay_order_id__icontains=value) |
            Q(razorpay_payment_id__icontains=value) |
            Q(registration__contact_name__icontains=value) |
            Q(registration__contact_email__icontains=value) |
            Q(registration__contact_phone__icontains=value)
        )
