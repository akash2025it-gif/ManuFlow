import logging
from decimal import Decimal
from django.utils import timezone
from .models import AuditLogEntry

logger = logging.getLogger(__name__)

# Keys that must never be recorded in audit logs
SENSITIVE_KEYS = {
    'password', 'confirm_password', 'current_password', 'new_password',
    'secret', 'token', 'key', 'auth_token', 'csrfmiddlewaretoken'
}


def sanitize_audit_details(data):
    """
    Recursively sanitize audit payload to prevent sensitive secrets or passwords
    from ever being stored in plain text or structured audit logs.
    Converts Decimals to float/string for JSON serialization.
    """
    if isinstance(data, dict):
        clean = {}
        for k, v in data.items():
            if any(s in str(k).lower() for s in SENSITIVE_KEYS):
                clean[k] = '***REDACTED***'
            elif isinstance(v, Decimal):
                clean[k] = str(v)
            elif isinstance(v, (dict, list)):
                clean[k] = sanitize_audit_details(v)
            else:
                clean[k] = v
        return clean
    elif isinstance(data, list):
        return [sanitize_audit_details(item) for item in data]
    elif isinstance(data, Decimal):
        return str(data)
    return data


def get_client_ip(request):
    """Extracts client IP address safely from request headers."""
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_audit_event(
    action,
    module,
    object_repr,
    user=None,
    object_id=None,
    reference_number='',
    details=None,
    request=None,
    ip_address=None
):
    """
    Central helper function to record a permanent audit trail entry.
    Handles user extraction, IP resolution, data sanitization, and graceful degradation.
    """
    try:
        resolved_user = user
        resolved_ip = ip_address

        if request:
            if not resolved_user and hasattr(request, 'user') and request.user.is_authenticated:
                resolved_user = request.user
            if not resolved_ip:
                resolved_ip = get_client_ip(request)

        clean_details = sanitize_audit_details(details or {})

        entry = AuditLogEntry.objects.create(
            user=resolved_user,
            action=action,
            module=module,
            object_repr=str(object_repr)[:255],
            object_id=str(object_id)[:100] if object_id else None,
            reference_number=str(reference_number)[:100] if reference_number else '',
            ip_address=resolved_ip,
            details=clean_details
        )
        return entry
    except Exception as exc:
        logger.error(f"Failed to record audit log for {action} on {object_repr}: {exc}", exc_info=True)
        return None
