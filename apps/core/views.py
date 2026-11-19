from datetime import date
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from django.http import JsonResponse

from apps.accounts.decorators import role_required
from apps.accounts.models import CustomUser
from .models import AuditLogEntry


def home_view(request):
    """
    Public landing page for NIT Trichy Order-to-Audit Management System.
    If user is authenticated, provides direct jump to their role dashboard.
    """
    if request.user.is_authenticated:
        return redirect('dashboard_home')
    return render(request, 'core/home.html', {
        'page_title': 'NIT Trichy | Order-to-Audit Management System',
    })


@login_required
@role_required(['AUDITOR', 'OWNER', 'ADMIN'])
def audit_trail_view(request):
    """
    Centralized System Audit Observatory.
    Displays tamper-evident records of all system events, state transitions,
    and business actions with filtering, search, and details inspection.
    """
    query = request.GET.get('q', '').strip()
    selected_module = request.GET.get('module', '').strip()
    selected_action = request.GET.get('action', '').strip()
    user_id = request.GET.get('user', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    entries = AuditLogEntry.objects.select_related('user').all()

    if query:
        entries = entries.filter(
            Q(object_repr__icontains=query) |
            Q(reference_number__icontains=query) |
            Q(user_email__icontains=query) |
            Q(details__icontains=query)
        )

    if selected_module:
        entries = entries.filter(module=selected_module)

    if selected_action:
        entries = entries.filter(action=selected_action)

    if user_id:
        entries = entries.filter(user_id=user_id)

    if date_from:
        entries = entries.filter(timestamp__date__gte=date_from)

    if date_to:
        entries = entries.filter(timestamp__date__lte=date_to)

    # Statistics for dashboard summary cards
    today = timezone.now().date()
    total_count = AuditLogEntry.objects.count()
    today_count = AuditLogEntry.objects.filter(timestamp__date=today).count()
    module_counts = AuditLogEntry.objects.values('module').annotate(count=Count('id')).order_by('-count')

    paginator = Paginator(entries, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    users_list = CustomUser.objects.filter(is_active=True).order_by('first_name', 'email')

    context = {
        'page_title': 'System Audit Trail & Compliance Observatory',
        'page_obj': page_obj,
        'query': query,
        'selected_module': selected_module,
        'selected_action': selected_action,
        'selected_user': user_id,
        'date_from': date_from,
        'date_to': date_to,
        'total_count': total_count,
        'today_count': today_count,
        'module_counts': module_counts,
        'modules': AuditLogEntry.Module.choices,
        'actions': AuditLogEntry.Action.choices,
        'users_list': users_list,
    }
    return render(request, 'core/audit_trail.html', context)


@login_required
@role_required(['AUDITOR', 'OWNER', 'ADMIN'])
def audit_trail_detail_view(request, pk):
    """
    Returns full details for a single audit record as JSON or HTML fragment.
    """
    entry = get_object_or_404(AuditLogEntry.objects.select_related('user'), pk=pk)
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
        return JsonResponse({
            'id': entry.id,
            'timestamp': entry.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'user': entry.user_email or 'System',
            'role': entry.user_role or 'System Service',
            'module': entry.get_module_display(),
            'action': entry.get_action_display(),
            'object_repr': entry.object_repr,
            'reference_number': entry.reference_number,
            'ip_address': entry.ip_address or 'Internal / Host',
            'details': entry.details
        })

    return render(request, 'core/audit_detail.html', {
        'page_title': f"Audit Entry #{entry.id}",
        'entry': entry,
    })


def custom_403_view(request, exception=None):
    """Custom 403 Forbidden handler."""
    return render(
        request,
        'core/403.html',
        {
            'exception': exception,
            'page_title': '403 Forbidden - Access Denied',
        },
        status=403,
    )


def custom_404_view(request, exception=None):
    """Custom 404 Not Found handler."""
    return render(
        request,
        'core/404.html',
        {
            'page_title': '404 Page Not Found',
        },
        status=404,
    )


def custom_500_view(request):
    """Custom 500 Internal Server Error handler."""
    return render(
        request,
        'core/500.html',
        {
            'page_title': '500 Server Error',
        },
        status=500,
    )
