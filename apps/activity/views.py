from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django import forms
import django_filters

from .models import ActivityLog


class ActivityLogFilter(django_filters.FilterSet):
    action    = django_filters.ChoiceFilter(
        choices=ActivityLog.ACTION_CHOICES,
        empty_label='All actions',
        label='Action',
    )
    date_from = django_filters.DateFilter(
        field_name='timestamp',
        lookup_expr='gte',
        label='From date',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    date_to   = django_filters.DateFilter(
        field_name='timestamp',
        lookup_expr='lte',
        label='To date',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    class Meta:
        model  = ActivityLog
        fields = ['action', 'date_from', 'date_to']


@login_required
def activity_log_list(request):
    if not request.user.is_staff:
        return redirect('admin_login')

    qs = ActivityLog.objects.select_related('actor').order_by('-timestamp')
    f  = ActivityLogFilter(request.GET, queryset=qs)
    return render(request, 'activity/list.html', {'filter': f, 'logs': f.qs[:200]})
