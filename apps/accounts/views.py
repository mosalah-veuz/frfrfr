from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from django.contrib import messages

from .forms import AdminLoginForm, UserLoginForm, UserProfileSignupForm, UserProfileForm
from .services import create_user_service


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
                if user.is_staff:
                    login(request, user)
                    next_url = request.GET.get('next')
                    if not next_url or next_url.strip() in ('', '/panel', '/panel/'):
                        next_url = 'admin_dashboard'
                    return redirect(next_url)
                else:
                    messages.error(request, 'Access denied. Admin credentials required.')
            else:
                messages.error(request, 'Invalid credentials.')

    return render(request, 'accounts/login.html', {
        'form': form,
        'locked': locked,
        'is_admin_login': True,
        'page_title': 'Admin Sign In',
        'page_subtitle': 'Access the administrative control panel'
    })


@require_http_methods(['GET', 'POST'])
def user_login(request):
    if request.user.is_authenticated:
        return redirect('portal')

    locked = request.GET.get('locked')
    form   = UserLoginForm()

    if request.method == 'POST':
        form = UserLoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
            )
            if user:
                login(request, user)
                next_url = request.GET.get('next')
                if not next_url or next_url.strip() in ('', '/login', '/login/', '/signup', '/signup/'):
                    next_url = 'portal'
                return redirect(next_url)
            else:
                messages.error(request, 'Invalid credentials.')

    return render(request, 'accounts/login.html', {
        'form': form,
        'locked': locked,
        'page_title': 'Sign In',
        'page_subtitle': 'Sign in to your account to book tickets'
    })


@require_http_methods(['GET', 'POST'])
def user_signup(request):
    if request.user.is_authenticated:
        return redirect('portal')

    form = UserProfileSignupForm()

    if request.method == 'POST':
        form = UserProfileSignupForm(request.POST)
        if form.is_valid():
            try:
                user = create_user_service(
                    username=form.cleaned_data['username'],
                    first_name=form.cleaned_data['first_name'],
                    last_name=form.cleaned_data['last_name'],
                    email=form.cleaned_data['email'],
                    phone=form.cleaned_data['phone'],
                    password=form.cleaned_data['password']
                )
                
                # Auto log in the registered user
                authenticated_user = authenticate(
                    request,
                    username=form.cleaned_data['username'],
                    password=form.cleaned_data['password']
                )
                if authenticated_user:
                    login(request, authenticated_user)
                
                next_url = request.GET.get('next', 'portal')
                return redirect(next_url)
            except Exception as exc:
                messages.error(request, f"Registration failed: {exc}")

    return render(request, 'accounts/signup.html', {'form': form})


@login_required
def admin_logout(request):
    logout(request)
    return redirect('admin_login')


@login_required
def admin_dashboard(request):
    if not request.user.is_staff:
        return redirect('admin_login')

    from apps.registrations.selectors import get_dashboard_stats_selector
    stats = get_dashboard_stats_selector()
    return render(request, 'accounts/dashboard.html', {'stats': stats})


@login_required(login_url='login')
def profile_view(request):
    """User profile page to edit name, email, and phone number details."""
    form = UserProfileForm(instance=request.user)
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile details have been updated.')
            return redirect('portal')
    return render(request, 'accounts/profile.html', {'form': form})

