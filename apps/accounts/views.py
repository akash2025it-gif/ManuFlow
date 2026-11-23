from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from .forms import LoginForm, UserProfileUpdateForm
from .models import CustomUser
from .decorators import admin_required


def login_view(request):
    """
    Handles user login. If authenticated, redirects to the role-based dashboard.
    Supports 1-click role demo authentication during DEMO_MODE.
    """
    if request.user.is_authenticated:
        return redirect('dashboard_home')

    next_url = request.GET.get('next', '')

    # 1-Click Role Demo Authentication in DEMO_MODE
    # Strictly prohibited in production: requires both DEBUG=True and DEMO_MODE=True.
    demo_role = request.GET.get('demo') or request.GET.get('role')
    demo_allowed = settings.DEBUG and getattr(settings, 'DEMO_MODE', False)
    if demo_allowed and demo_role:
        role_email_map = {
            'admin': 'admin@nit.edu',
            'salesman': 'salesman@nit.edu',
            'production': 'production@nit.edu',
            'auditor': 'auditor@nit.edu',
            'owner': 'owner@nit.edu',
            'accountant': 'accountant@nit.edu',
        }
        target_email = role_email_map.get(demo_role.lower())
        if target_email:
            try:
                demo_user = CustomUser.objects.get(email=target_email, is_active=True)
                login(request, demo_user, backend='apps.accounts.backends.EmailOrUsernameBackend')
                messages.success(
                    request,
                    f"Authenticated as {demo_user.get_full_name() or demo_user.username} ({demo_user.get_role_display()})."
                )
                if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                    return redirect(next_url)
                return redirect(demo_user.get_dashboard_name())
            except CustomUser.DoesNotExist:
                pass

    if request.method == 'POST':
        form = LoginForm(request=request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            # Session expiry handling based on remember_me
            if form.cleaned_data.get('remember_me'):
                # 2 weeks
                request.session.set_expiry(1209600)
            else:
                # Browser close
                request.session.set_expiry(0)

            messages.success(
                request,
                f"Welcome back, {user.get_full_name() or user.username}! "
                f"Logged in as {user.get_role_display()}."
            )

            # Redirect to next URL or directly to user's role dashboard
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)

            return redirect(user.get_dashboard_name())
        else:
            messages.error(request, "Authentication failed. Please verify your credentials.")
    else:
        form = LoginForm(request=request)

    context = {
        'form': form,
        'next': next_url,
        'page_title': 'Sign In | ManuFlow',
    }
    return render(request, 'accounts/login.html', context)


@require_POST
def logout_view(request):
    """
    Logs out the current user and redirects to login with confirmation message.
    Accepts POST only, preventing cross-site requests from logging a user out.
    """
    if request.user.is_authenticated:
        user_name = request.user.get_full_name() or request.user.username
        logout(request)
        messages.info(request, f"You have been securely signed out, {user_name}.")
    return redirect('login')


@login_required
def profile_view(request):
    """
    User self-service profile page to view role assignment and update contact details.
    """
    user = request.user
    if request.method == 'POST':
        form = UserProfileUpdateForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile information has been successfully updated.")
            return redirect('profile')
    else:
        form = UserProfileUpdateForm(instance=user)

    context = {
        'form': form,
        'user_obj': user,
        'page_title': 'My Profile | ManuFlow',
    }
    return render(request, 'accounts/profile.html', context)


@admin_required
def user_list_view(request):
    """
    Admin-only view to inspect all system users, assigned roles, and access states.
    """
    users = CustomUser.objects.all().order_by('-date_joined')
    context = {
        'users': users,
        'page_title': 'User Management & Roles | Admin Portal',
    }
    return render(request, 'accounts/user_list.html', context)
