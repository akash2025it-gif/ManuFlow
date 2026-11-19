from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from apps.accounts.models import CustomUser


def can_view_master_data(view_func):
    """All authenticated system roles can view master data."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={request.path}")
        return view_func(request, *args, **kwargs)
    return _wrapped


def can_manage_products(view_func):
    """Admin, Production Manager, and Owner can create/edit Products and Pack sizes."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={request.path}")
        if request.user.is_superuser or request.user.role in [
            CustomUser.Role.ADMIN,
            CustomUser.Role.PRODUCTION,
            CustomUser.Role.OWNER,
        ]:
            return view_func(request, *args, **kwargs)
        raise PermissionDenied("Only Production Managers, System Administrators, or Owners can modify product catalogs.")
    return _wrapped


def can_manage_bom(view_func):
    """Admin, Production Manager, and Owner can create/edit Bill of Materials (BOM)."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={request.path}")
        if request.user.is_superuser or request.user.role in [
            CustomUser.Role.ADMIN,
            CustomUser.Role.PRODUCTION,
            CustomUser.Role.OWNER,
        ]:
            return view_func(request, *args, **kwargs)
        raise PermissionDenied("Only Production Managers, System Administrators, or Owners can modify Bills of Materials.")
    return _wrapped


def can_manage_materials(view_func):
    """Admin, Production Manager, and Owner can create/edit Raw & Packaging Materials."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={request.path}")
        if request.user.is_superuser or request.user.role in [
            CustomUser.Role.ADMIN,
            CustomUser.Role.PRODUCTION,
            CustomUser.Role.OWNER,
        ]:
            return view_func(request, *args, **kwargs)
        raise PermissionDenied("Only Production Managers, System Administrators, or Owners can modify material master records.")
    return _wrapped


def can_manage_customers(view_func):
    """Admin, Salesman, and Owner can create/edit Customers (Retailers & Distributors)."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={request.path}")
        if request.user.is_superuser or request.user.role in [
            CustomUser.Role.ADMIN,
            CustomUser.Role.SALESMAN,
            CustomUser.Role.OWNER,
        ]:
            return view_func(request, *args, **kwargs)
        raise PermissionDenied("Only Sales Representatives, System Administrators, or Owners can modify customer master records.")
    return _wrapped


def can_manage_suppliers(view_func):
    """Admin, Production, and Owner can create/edit Suppliers."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={request.path}")
        if request.user.is_superuser or request.user.role in [
            CustomUser.Role.ADMIN,
            CustomUser.Role.PRODUCTION,
            CustomUser.Role.OWNER,
        ]:
            return view_func(request, *args, **kwargs)
        raise PermissionDenied("Only Production Managers, System Administrators, or Owners can modify supplier records.")
    return _wrapped


def can_manage_uom(view_func):
    """Admin, Production, and Owner can create/edit UOMs and Unit Conversions."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={request.path}")
        if request.user.is_superuser or request.user.role in [
            CustomUser.Role.ADMIN,
            CustomUser.Role.PRODUCTION,
            CustomUser.Role.OWNER,
        ]:
            return view_func(request, *args, **kwargs)
        raise PermissionDenied("Only Production Managers, System Administrators, or Owners can modify units of measurement.")
    return _wrapped
