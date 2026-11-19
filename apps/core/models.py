from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone


class AuditLogQuerySet(models.QuerySet):
    """QuerySet that strictly prevents bulk updates and deletions of audit records."""
    
    def delete(self):
        raise ValidationError("Bulk deletion of audit trail records is strictly prohibited.")
        
    def update(self, **kwargs):
        raise ValidationError("Bulk modification of audit trail records is strictly prohibited.")


class AuditLogManager(models.Manager):
    def get_queryset(self):
        return AuditLogQuerySet(self.model, using=self._db)


class AuditLogEntry(models.Model):
    """
    Centralized, tamper-resistant system audit trail for all critical business actions.
    Records who did what, when, in which module, with what reference, and before/after details.
    Guaranteed immutable once committed to the database.
    """
    class Action(models.TextChoices):
        # Authentication
        LOGIN = 'LOGIN', 'User Login'
        LOGOUT = 'LOGOUT', 'User Logout'
        
        # Master Data
        MASTER_DATA_CREATE = 'MASTER_DATA_CREATE', 'Master Data Created'
        MASTER_DATA_UPDATE = 'MASTER_DATA_UPDATE', 'Master Data Updated'
        MASTER_DATA_DELETE = 'MASTER_DATA_DELETE', 'Master Data Deleted'
        
        # Inventory & Purchasing
        PO_CREATED = 'PO_CREATED', 'Purchase Order Created'
        PO_APPROVED = 'PO_APPROVED', 'Purchase Order Approved'
        GRN_POSTED = 'GRN_POSTED', 'Goods Receipt Posted'
        STOCK_ADJUSTMENT = 'STOCK_ADJUSTMENT', 'Stock Adjustment Posted'
        
        # Production
        PRODUCTION_CREATE = 'PRODUCTION_CREATE', 'Production Run Created'
        PRODUCTION_POST = 'PRODUCTION_POST', 'Production Run Completed & Posted'
        
        # Sales
        ORDER_CREATED = 'ORDER_CREATED', 'Sales Order Created'
        ORDER_APPROVED = 'ORDER_APPROVED', 'Sales Order Approved'
        ORDER_REJECTED = 'ORDER_REJECTED', 'Sales Order Rejected'
        INVOICE_GENERATED = 'INVOICE_GENERATED', 'Tax Invoice Generated'
        DISPATCH_RECORDED = 'DISPATCH_RECORDED', 'Goods Dispatched'
        
        # Finance & Accounts
        PAYMENT_RECORDED = 'PAYMENT_RECORDED', 'Customer Payment Recorded'
        
        # Other
        SYSTEM_EVENT = 'SYSTEM_EVENT', 'System Event'

    class Module(models.TextChoices):
        AUTH = 'AUTH', 'Authentication & Access'
        MASTER_DATA = 'MASTER_DATA', 'Master Data'
        INVENTORY = 'INVENTORY', 'Inventory & Purchasing'
        PRODUCTION = 'PRODUCTION', 'Production'
        SALES = 'SALES', 'Sales & Invoicing'
        FINANCE = 'FINANCE', 'Finance & Accounts'
        SYSTEM = 'SYSTEM', 'System'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_entries',
        help_text='User who triggered the action (or null for automated system tasks)'
    )
    user_email = models.CharField(max_length=255, blank=True, help_text='Cached user email at event time')
    user_role = models.CharField(max_length=50, blank=True, help_text='Cached user role at event time')
    
    action = models.CharField(max_length=50, choices=Action.choices, db_index=True)
    module = models.CharField(max_length=50, choices=Module.choices, db_index=True)
    
    object_repr = models.CharField(max_length=255, help_text='Human-readable name or code of object')
    object_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    
    # Traceable link references (e.g. stock ledger, invoice, payment, production run)
    reference_number = models.CharField(max_length=100, blank=True, db_index=True, help_text='Linked transaction reference')
    
    # Network context
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    # Audit Payload (before/after states, changes, quantities, amounts, notes)
    details = models.JSONField(default=dict, blank=True)
    
    timestamp = models.DateTimeField(default=timezone.now, db_index=True, editable=False)

    objects = AuditLogManager()

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Audit Trail Entry'
        verbose_name_plural = 'Audit Trail Entries'
        indexes = [
            models.Index(fields=['module', 'action']),
            models.Index(fields=['timestamp', 'module']),
            models.Index(fields=['reference_number']),
        ]

    def save(self, *args, **kwargs):
        # Enforce immutability: updates to existing audit entries are strictly forbidden
        if self.pk is not None:
            raise ValidationError("Audit trail records are strictly immutable and cannot be updated.")
        
        if self.user and not self.user_email:
            self.user_email = self.user.email
            self.user_role = getattr(self.user, 'role', '')
            
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Enforce immutability: deletions are strictly forbidden
        raise ValidationError("Audit trail records are permanent and cannot be deleted.")

    def __str__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {self.module} - {self.action} by {self.user_email or 'System'} on {self.object_repr}"
