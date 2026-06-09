from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from django.contrib import messages

from .forms import AdminLoginForm


@require_http_methods(['GET', 'POST'])
def admin_login(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('admin_dashboard')

    locked = request.GET.get('locked')
    form   = AdminLoginForm()

    if request.method == 'POST':
        form = AdminLoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
            )
            if user:
                login(request, user)
                if user.is_staff:
                    next_url = request.GET.get('next', 'admin_dashboard')
                else:
                    next_url = request.GET.get('next', 'portal')
                return redirect(next_url)
            else:
                messages.error(request, 'Invalid credentials.')

    return render(request, 'accounts/login.html', {'form': form, 'locked': locked})


@login_required
def admin_logout(request):
    logout(request)
    return redirect('portal')


@login_required
def admin_dashboard(request):
    if not request.user.is_staff:
        return redirect('admin_login')

    from apps.tickets.models import Ticket
    from apps.registrations.models import Registration
    from django.utils import timezone

    stats = {
        'total_tickets':       Ticket.objects.filter(is_active=True).count(),
        'total_registrations': Registration.objects.filter(status='completed').count(),
        'incomplete':          Registration.objects.filter(
            status__in=['pending', 'processing'],
            created_at__lte=timezone.now() - timezone.timedelta(minutes=30)
        ).count(),
        'total_revenue': sum(
            r.total_amount for r in Registration.objects.filter(
                status='completed'
            ).prefetch_related('items')
        ),
    }
    return render(request, 'accounts/dashboard.html', {'stats': stats})


@login_required
def profile_view(request):
    """User profile page to edit name, email, and phone number details."""
    from .forms import UserProfileForm
    form = UserProfileForm(instance=request.user)
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile details have been updated.')
            return redirect('portal')
    return render(request, 'accounts/profile.html', {'form': form})
