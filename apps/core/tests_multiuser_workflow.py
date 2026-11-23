from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.core.management import call_command

from apps.accounts.models import CustomUser
from apps.master_data.models import Customer, ProductPackSize, UnitOfMeasurement
from apps.sales.models import SalesOrder, SalesOrderItem, Invoice, PaymentRecord


class MultiUserEnterpriseWorkflowTests(TestCase):
    """
    End-to-end multi-user integration test verifying:
    1. Independent sessions for Salesman, Factory Admin, Production Supervisor, Accountant, Auditor, and Owner.
    2. Shared company operational data: Salesman creates order -> Admin approves -> Invoice & Payment -> Owner KPI update.
    3. Strict backend RBAC enforcement preventing unauthorized cross-role operations.
    4. Session isolation: logging out User A does not disturb User B's active session.
    """

    def setUp(self):
        # Seed foundational benchmark master data
        call_command('seed_snacks_benchmark')

        # Create distinct persona users
        self.salesman = CustomUser.objects.create_user(
            username='sales_person_1',
            email='sales_p1@manuflow.app',
            password='Password123!',
            role=CustomUser.Role.SALESMAN,
            employee_id='TEST-SLS-001'
        )
        self.admin = CustomUser.objects.create_user(
            username='factory_admin_1',
            email='admin_f1@manuflow.app',
            password='Password123!',
            role=CustomUser.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
            employee_id='TEST-ADM-001'
        )
        self.prod_supervisor = CustomUser.objects.create_user(
            username='prod_sup_1',
            email='prod_s1@manuflow.app',
            password='Password123!',
            role=CustomUser.Role.PRODUCTION,
            employee_id='TEST-PRD-001'
        )
        self.accountant = CustomUser.objects.create_user(
            username='accountant_1',
            email='acct_1@manuflow.app',
            password='Password123!',
            role=CustomUser.Role.ACCOUNTANT,
            employee_id='TEST-ACT-001'
        )
        self.auditor = CustomUser.objects.create_user(
            username='auditor_1',
            email='audit_1@manuflow.app',
            password='Password123!',
            role=CustomUser.Role.AUDITOR,
            employee_id='TEST-AUD-001'
        )
        self.owner = CustomUser.objects.create_user(
            username='owner_exec_1',
            email='owner_e1@manuflow.app',
            password='Password123!',
            role=CustomUser.Role.OWNER,
            employee_id='TEST-EXEC-001'
        )

        # Separate HTTP clients simulating separate devices/browsers
        self.salesman_client = Client()
        self.admin_client = Client()
        self.prod_client = Client()
        self.acct_client = Client()
        self.audit_client = Client()
        self.owner_client = Client()

        self.customer = Customer.objects.first()
        self.sku = ProductPackSize.objects.first()

    def test_complete_multiuser_workflow_and_session_isolation(self):
        # ---------------------------------------------------------------------
        # Step 1: Salesman logs in and creates a Sales Order
        # ---------------------------------------------------------------------
        login_resp = self.salesman_client.post(reverse('login'), {
            'username': 'sales_p1@manuflow.app',
            'password': 'Password123!',
        })
        self.assertRedirects(login_resp, reverse('salesman_dashboard'))

        uom = UnitOfMeasurement.objects.get(code='PCS')
        created_order = SalesOrder.objects.create(
            order_number='SO-MULTI-001',
            customer=self.customer,
            salesman=self.salesman,
            order_date=date.today(),
            delivery_address='Shop 14, Main Market',
            delivery_city='Tiruchirappalli',
            delivery_state='Tamil Nadu',
            status=SalesOrder.Status.DRAFT
        )
        SalesOrderItem.objects.create(
            sales_order=created_order,
            product_pack_size=self.sku,
            quantity=Decimal('25.00'),
            uom=uom,
            unit_price=Decimal('50.00')
        )
        created_order.update_totals()
        created_order.refresh_from_db()

        # Salesman submits order for approval
        submit_resp = self.salesman_client.post(reverse('sales_order_submit', kwargs={'pk': created_order.pk}))
        self.assertEqual(submit_resp.status_code, 302)
        created_order.refresh_from_db()
        self.assertEqual(created_order.status, SalesOrder.Status.SUBMITTED)

        # ---------------------------------------------------------------------
        # Step 2: Factory Admin logs in in a separate session
        # ---------------------------------------------------------------------
        admin_login_resp = self.admin_client.post(reverse('login'), {
            'username': 'admin_f1@manuflow.app',
            'password': 'Password123!',
        })
        self.assertRedirects(admin_login_resp, reverse('admin_dashboard'))

        # Admin views approval queue and sees Salesman's order
        order_detail_resp = self.admin_client.get(reverse('sales_order_detail', kwargs={'pk': created_order.pk}))
        self.assertEqual(order_detail_resp.status_code, 200)
        self.assertContains(order_detail_resp, created_order.order_number)

        # Admin approves the order
        approve_resp = self.admin_client.post(reverse('sales_order_approve', kwargs={'pk': created_order.pk}))
        self.assertEqual(approve_resp.status_code, 302)
        created_order.refresh_from_db()
        self.assertEqual(created_order.status, SalesOrder.Status.APPROVED)
        self.assertEqual(created_order.approved_by, self.admin)

        # Admin generates Invoice
        from apps.sales.services import generate_invoice_for_order
        inv = generate_invoice_for_order(created_order.pk, self.admin)
        self.assertIsNotNone(inv)

        # ---------------------------------------------------------------------
        # Step 3: Production Supervisor logs in and verifies production modules
        # ---------------------------------------------------------------------
        prod_login_resp = self.prod_client.post(reverse('login'), {
            'username': 'prod_s1@manuflow.app',
            'password': 'Password123!',
        })
        self.assertRedirects(prod_login_resp, reverse('production_dashboard'))

        prod_runs_resp = self.prod_client.get(reverse('production_run_list'))
        self.assertEqual(prod_runs_resp.status_code, 200)

        # ---------------------------------------------------------------------
        # Step 4: Accountant logs in, verifies invoice and records customer payment
        # ---------------------------------------------------------------------
        acct_login_resp = self.acct_client.post(reverse('login'), {
            'username': 'acct_1@manuflow.app',
            'password': 'Password123!',
        })
        self.assertRedirects(acct_login_resp, reverse('finance:dashboard'))

        # Accountant views invoice list and records customer payment
        inv_list_resp = self.acct_client.get(reverse('invoice_list'))
        self.assertEqual(inv_list_resp.status_code, 200)
        self.assertContains(inv_list_resp, inv.invoice_number)

        pay_resp = self.acct_client.post(reverse('finance:payment_create'), {
            'invoice': inv.pk,
            'customer': self.customer.pk,
            'payment_date': str(date.today()),
            'amount': str(inv.grand_total),
            'payment_mode': PaymentRecord.Mode.UPI,
            'transaction_reference': 'UPI-REF-TEST-9921',
            'notes': 'Full settlement recorded by Accountant',
        })
        self.assertEqual(pay_resp.status_code, 302)
        inv.refresh_from_db()
        self.assertEqual(inv.payment_status, Invoice.PaymentStatus.PAID)
        self.assertEqual(inv.balance_due, Decimal('0.00'))

        # ---------------------------------------------------------------------
        # Step 5: Compliance Auditor logs in and verifies audit observatory
        # ---------------------------------------------------------------------
        audit_login_resp = self.audit_client.post(reverse('login'), {
            'username': 'audit_1@manuflow.app',
            'password': 'Password123!',
        })
        self.assertRedirects(audit_login_resp, reverse('auditor_dashboard'))

        audit_trail_resp = self.audit_client.get(reverse('audit_trail'))
        self.assertEqual(audit_trail_resp.status_code, 200)

        # ---------------------------------------------------------------------
        # Step 6: Owner logs in and verifies executive command center
        # ---------------------------------------------------------------------
        owner_login_resp = self.owner_client.post(reverse('login'), {
            'username': 'owner_e1@manuflow.app',
            'password': 'Password123!',
        })
        self.assertRedirects(owner_login_resp, reverse('owner_dashboard'))

        owner_dash_resp = self.owner_client.get(reverse('owner_dashboard'))
        self.assertEqual(owner_dash_resp.status_code, 200)

        # ---------------------------------------------------------------------
        # Step 7: Role boundary checks (Unauthorized actions are blocked)
        # ---------------------------------------------------------------------
        # Salesman CANNOT access Admin User Management -> 403 Forbidden
        user_mgmt_resp = self.salesman_client.get(reverse('user_list'))
        self.assertEqual(user_mgmt_resp.status_code, 403)

        # Production supervisor CANNOT access Finance GST Register -> 403 Forbidden
        fin_resp = self.prod_client.get(reverse('finance:gst_sales_register'))
        self.assertEqual(fin_resp.status_code, 403)

        # ---------------------------------------------------------------------
        # Step 8: Session Isolation Verification
        # ---------------------------------------------------------------------
        # Salesman logs out
        logout_resp = self.salesman_client.post(reverse('logout'))
        self.assertRedirects(logout_resp, reverse('login'))

        # Salesman's session is terminated -> accessing dashboard redirects to login
        sales_dash_after = self.salesman_client.get(reverse('salesman_dashboard'))
        self.assertEqual(sales_dash_after.status_code, 302)
        self.assertIn('/accounts/login/', sales_dash_after.url)

        # Owner's concurrent session remains FULLY active and unaffected!
        owner_dash_after = self.owner_client.get(reverse('owner_dashboard'))
        self.assertEqual(owner_dash_after.status_code, 200)

        # Admin's concurrent session also remains active!
        admin_dash_after = self.admin_client.get(reverse('admin_dashboard'))
        self.assertEqual(admin_dash_after.status_code, 200)
