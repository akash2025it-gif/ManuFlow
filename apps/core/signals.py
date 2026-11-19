import logging
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from .audit import log_audit_event, get_client_ip
from .models import AuditLogEntry

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def audit_user_login(sender, request, user, **kwargs):
    """Logs user login events with IP and timestamp."""
    try:
        ip = get_client_ip(request)
        log_audit_event(
            action=AuditLogEntry.Action.LOGIN,
            module=AuditLogEntry.Module.AUTH,
            object_repr=f"User {user.email}",
            user=user,
            object_id=str(user.pk),
            ip_address=ip,
            details={
                'role': getattr(user, 'role', ''),
                'full_name': user.get_full_name() or user.username,
                'event': 'Successful authentication'
            }
        )
    except Exception as e:
        logger.error(f"Error logging login event: {e}")


@receiver(user_logged_out)
def audit_user_logout(sender, request, user, **kwargs):
    """Logs user logout events."""
    try:
        if user and user.is_authenticated:
            ip = get_client_ip(request)
            log_audit_event(
                action=AuditLogEntry.Action.LOGOUT,
                module=AuditLogEntry.Module.AUTH,
                object_repr=f"User {user.email}",
                user=user,
                object_id=str(user.pk),
                ip_address=ip,
                details={
                    'role': getattr(user, 'role', ''),
                    'event': 'User session terminated'
                }
            )
    except Exception as e:
        logger.error(f"Error logging logout event: {e}")
