from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.db.models import Q

from .forms import (
    LoginForm,
    UserProfileUpdateForm,
    StaffUserCreateForm,
    StaffUserEditForm,
)
from .models import CustomUser
from .decorators import admin_required, role_required


def login_view(request):
    """
    Handles user login.
    - If user is already authenticated: directly redirects to requested 'next' URL (if safe) or their role dashboard.
    - If credentials are valid: logs user in, handles remember_me session lifetime, and redirects to requested 'next' URL or role dashboard.
    - Preserves 'next' across both GET and POST requests.
    """
    next_url = request.POST.get('next') or request.GET.get('next', '').strip()

    if request.user.is_authenticated:
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            return redirect(next_url)
        return redirect(request.user.get_dashboard_name())

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
            'owner': 'demo@manuflow.app',
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
    Logs out the current user, invalidates the server-side session,
    clears authentication cookies, and sets strict cache-control headers.
    """
    if request.user.is_authenticated:
        user_name = request.user.get_full_name() or request.user.username
        logout(request)
        messages.info(request, f"You have been securely signed out, {user_name}.")

    response = redirect('login')
    response.delete_cookie(settings.SESSION_COOKIE_NAME)
    response.delete_cookie('sessionid')
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


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


@role_required(['ADMIN', 'OWNER'])
def user_list_view(request):
    """
    Admin & Owner view to inspect all system staff accounts, filter by role/status,
    search employees, and manage accounts.
    """
    query = request.GET.get('q', '').strip()
    role_filter = request.GET.get('role', '').strip()
    status_filter = request.GET.get('status', '').strip()

    users = CustomUser.objects.all().order_by('-date_joined')

    if query:
        users = users.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(username__icontains=query) |
            Q(email__icontains=query) |
            Q(employee_id__icontains=query) |
            Q(department__icontains=query)
        )

    if role_filter:
        users = users.filter(role=role_filter)

    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)

    role_counts = {
        'all': CustomUser.objects.count(),
        'admin': CustomUser.objects.filter(role=CustomUser.Role.ADMIN).count(),
        'salesman': CustomUser.objects.filter(role=CustomUser.Role.SALESMAN).count(),
        'production': CustomUser.objects.filter(role=CustomUser.Role.PRODUCTION).count(),
        'auditor': CustomUser.objects.filter(role=CustomUser.Role.AUDITOR).count(),
        'owner': CustomUser.objects.filter(role=CustomUser.Role.OWNER).count(),
        'accountant': CustomUser.objects.filter(role=CustomUser.Role.ACCOUNTANT).count(),
    }

    context = {
        'users': users,
        'query': query,
        'role_filter': role_filter,
        'status_filter': status_filter,
        'role_counts': role_counts,
        'total_active': CustomUser.objects.filter(is_active=True).count(),
        'roles': CustomUser.Role.choices,
        'page_title': 'Staff Management & Role Directory | Admin Portal',
    }
    return render(request, 'accounts/user_list.html', context)


@role_required(['ADMIN', 'OWNER'])
def user_create_view(request):
    """
    Provision a new employee user account with assigned role and department.
    """
    if request.method == 'POST':
        form = StaffUserCreateForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            messages.success(
                request,
                f"Employee account for {new_user.get_full_name() or new_user.username} "
                f"({new_user.get_role_display()}) successfully created."
            )
            return redirect('user_list')
    else:
        form = StaffUserCreateForm()

    context = {
        'form': form,
        'is_edit': False,
        'page_title': 'Provision New Employee Account | ManuFlow',
    }
    return render(request, 'accounts/user_form.html', context)


@role_required(['ADMIN', 'OWNER'])
def user_edit_view(request, pk):
    """
    Edit existing employee account details, role assignment, and active status.
    """
    target_user = get_object_or_404(CustomUser, pk=pk)

    if request.method == 'POST':
        form = StaffUserEditForm(request.POST, instance=target_user)
        if form.is_valid():
            # Safeguard: prevent deactivating own active logged-in admin account
            if target_user == request.user and not form.cleaned_data.get('is_active'):
                messages.error(request, "Security guard: You cannot deactivate your own active session.")
                return redirect('user_edit', pk=target_user.pk)

            updated_user = form.save()
            messages.success(
                request,
                f"Employee details for {updated_user.get_full_name() or updated_user.username} successfully updated."
            )
            return redirect('user_list')
    else:
        form = StaffUserEditForm(instance=target_user)

    context = {
        'form': form,
        'target_user': target_user,
        'is_edit': True,
        'page_title': f'Edit Employee: {target_user.get_full_name() or target_user.username} | ManuFlow',
    }
    return render(request, 'accounts/user_form.html', context)


@role_required(['ADMIN', 'OWNER'])
@require_POST
def user_toggle_status_view(request, pk):
    """
    Quickly toggle an employee's account between Active and Suspended states.
    """
    target_user = get_object_or_404(CustomUser, pk=pk)

    if target_user == request.user:
        messages.error(request, "Security guard: You cannot suspend your own account.")
        return redirect('user_list')

    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=['is_active'])

    state_str = "activated" if target_user.is_active else "suspended"
    messages.success(
        request,
        f"Employee account for {target_user.get_full_name() or target_user.username} has been {state_str}."
    )
    return redirect('user_list')
