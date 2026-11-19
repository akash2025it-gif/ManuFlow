from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages


def role_required(allowed_roles):
    """
    Decorator for views that checks whether a user has one of the allowed roles.
    If not logged in, redirects to login page.
    If logged in without permissions, raises PermissionDenied (403).
    Superusers always have access.
    """
    if isinstance(allowed_roles, str):
        allowed_roles = [allowed_roles]

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(f"/accounts/login/?next={request.path}")

            # Admin or Superuser bypass for administrative supervision if needed
            if request.user.is_superuser or request.user.role == 'OWNER':
                return view_func(request, *args, **kwargs)

            if request.user.role in allowed_roles:
                return view_func(request, *args, **kwargs)

            # Raise HTTP 403 PermissionDenied
            raise PermissionDenied(
                f"Access denied. This view requires one of the following roles: {', '.join(allowed_roles)}."
            )

        return _wrapped_view

    return decorator


def admin_required(view_func):
    """Restricted to Admin and Superuser."""
    return role_required(['ADMIN'])(view_func)


def salesman_required(view_func):
    """Restricted to Salesman."""
    return role_required(['SALESMAN'])(view_func)


def production_required(view_func):
    """Restricted to Production."""
    return role_required(['PRODUCTION'])(view_func)


def auditor_required(view_func):
    """Restricted to Auditor."""
    return role_required(['AUDITOR'])(view_func)


def accountant_required(view_func):
    """Restricted to Accountant, Admin, and Owner."""
    return role_required(['ACCOUNTANT', 'ADMIN', 'OWNER'])(view_func)


def owner_required(view_func):
    """Restricted to Owner."""
    return role_required(['OWNER'])(view_func)
