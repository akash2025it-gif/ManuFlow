from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from apps.accounts.models import CustomUser
from apps.core.models import AuditLogEntry
from apps.core.audit import log_audit_event, sanitize_audit_details

User = get_user_model()


class AuditTrailModelSecurityTests(TestCase):
    """
    Tests ensuring that the audit trail is permanently immutable and protected
    against modification, deletion, or bulk alterations by any user or routine.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='auditor_sec_u',
            email='auditor_sec@nit.edu',
            password='TestPassword123!',
            role=CustomUser.Role.AUDITOR
        )
        self.entry = AuditLogEntry.objects.create(
            user=self.user,
            action=AuditLogEntry.Action.LOGIN,
            module=AuditLogEntry.Module.AUTH,
            object_repr="User auditor_sec@nit.edu",
            object_id=str(self.user.pk),
            reference_number="REF-001",
            details={'ip': '127.0.0.1', 'status': 'success'}
        )

    def test_prevent_individual_record_update(self):
        """Calling save() on an existing record must raise ValidationError."""
        self.entry.object_repr = "Tampered Representation"
        with self.assertRaises(ValidationError) as ctx:
            self.entry.save()
        self.assertIn("strictly immutable", str(ctx.exception))

    def test_prevent_individual_record_deletion(self):
        """Calling delete() on a record must raise ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            self.entry.delete()
        self.assertIn("permanent and cannot be deleted", str(ctx.exception))

    def test_prevent_bulk_record_deletion(self):
        """Calling delete() on an AuditLogEntry QuerySet must raise ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            AuditLogEntry.objects.filter(pk=self.entry.pk).delete()
        self.assertIn("Bulk deletion of audit trail records is strictly prohibited", str(ctx.exception))

    def test_prevent_bulk_record_update(self):
        """Calling update() on an AuditLogEntry QuerySet must raise ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            AuditLogEntry.objects.filter(pk=self.entry.pk).update(object_repr='Hacked')
        self.assertIn("Bulk modification of audit trail records is strictly prohibited", str(ctx.exception))


class AuditTrailSanitizationTests(TestCase):
    """
    Tests ensuring sensitive fields (passwords, tokens, secrets) are redacted
    before being committed to audit trail entries.
    """

    def test_sensitive_keys_redacted(self):
        payload = {
            'username': 'admin_nit',
            'password': 'SuperSecretPassword!',
            'api_token': 'sk-123456789',
            'nested': {
                'secret_key': 'topsecret',
                'amount': Decimal('500.00')
            }
        }
        clean = sanitize_audit_details(payload)
        self.assertEqual(clean['username'], 'admin_nit')
        self.assertEqual(clean['password'], '***REDACTED***')
        self.assertEqual(clean['api_token'], '***REDACTED***')
        self.assertEqual(clean['nested']['secret_key'], '***REDACTED***')
        self.assertEqual(clean['nested']['amount'], '500.00')


class AuditTrailViewAndRBACTests(TestCase):
    """
    Tests role-based access control for the audit trail view:
    - Auditor, Owner, Admin: HTTP 200
    - Salesman, Production: HTTP 403 Forbidden
    - Anonymous: HTTP 302 Redirect to Login
    """

    def setUp(self):
        self.client = Client()
        self.password = 'TestPassword123!'

        self.admin = User.objects.create_user(
            username='admin_aud_u', email='admin_aud@nit.edu', password=self.password, role=CustomUser.Role.ADMIN
        )
        self.owner = User.objects.create_user(
            username='owner_aud_u', email='owner_aud@nit.edu', password=self.password, role=CustomUser.Role.OWNER
        )
        self.auditor = User.objects.create_user(
            username='auditor_aud_u', email='auditor_aud@nit.edu', password=self.password, role=CustomUser.Role.AUDITOR
        )
        self.salesman = User.objects.create_user(
            username='salesman_aud_u', email='salesman_aud@nit.edu', password=self.password, role=CustomUser.Role.SALESMAN
        )
        self.production = User.objects.create_user(
            username='production_aud_u', email='production_aud@nit.edu', password=self.password, role=CustomUser.Role.PRODUCTION
        )

        # Seed sample audit entries
        log_audit_event(
            action=AuditLogEntry.Action.LOGIN,
            module=AuditLogEntry.Module.AUTH,
            object_repr="User admin_aud@nit.edu",
            user=self.admin,
            reference_number="AUTH-01"
        )
        log_audit_event(
            action=AuditLogEntry.Action.ORDER_APPROVED,
            module=AuditLogEntry.Module.SALES,
            object_repr="Sales Order SO-2026-001",
            user=self.admin,
            reference_number="SO-2026-001",
            details={'total': '7875.00'}
        )

    def test_anonymous_redirected_to_login(self):
        res = self.client.get(reverse('audit_trail'))
        self.assertEqual(res.status_code, 302)
        self.assertIn('/accounts/login/', res.url)

    def test_auditor_access_granted(self):
        self.client.login(username='auditor_aud_u', password=self.password)
        res = self.client.get(reverse('audit_trail'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "System Audit Trail")
        self.assertContains(res, "SO-2026-001")

    def test_owner_access_granted(self):
        self.client.login(username='owner_aud_u', password=self.password)
        res = self.client.get(reverse('audit_trail'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "System Audit Trail")

    def test_admin_access_granted(self):
        self.client.login(username='admin_aud_u', password=self.password)
        res = self.client.get(reverse('audit_trail'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "System Audit Trail")

    def test_salesman_access_forbidden(self):
        self.client.login(username='salesman_aud_u', password=self.password)
        res = self.client.get(reverse('audit_trail'))
        self.assertEqual(res.status_code, 403)

    def test_production_access_forbidden(self):
        self.client.login(username='production_aud_u', password=self.password)
        res = self.client.get(reverse('audit_trail'))
        self.assertEqual(res.status_code, 403)

    def test_audit_filtering_by_module(self):
        self.client.login(username='auditor_aud_u', password=self.password)
        res = self.client.get(reverse('audit_trail') + '?module=SALES')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "SO-2026-001")

    def test_audit_detail_json_view(self):
        self.client.login(username='auditor_aud_u', password=self.password)
        entry = AuditLogEntry.objects.first()
        res = self.client.get(reverse('audit_trail_detail', kwargs={'pk': entry.pk}) + '?format=json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['id'], entry.id)
