from decimal import Decimal
from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from django.core.management import call_command

from apps.accounts.models import CustomUser
from apps.master_data.models import Customer, ProductPackSize, UnitOfMeasurement
from apps.sales.models import SalesOrder, SalesOrderItem, Invoice, PaymentRecord
from apps.sales.services import generate_sales_order_number, generate_invoice_for_order, record_invoice_payment
from apps.production.models import ProductionRun
from apps.inventory.models import StockItem


class DashboardRoleAccessTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = 'Pass12345!'
        self.admin = CustomUser.objects.create_user(
            email='admin@nit.edu', username='admin_u', password=self.password,
            role=CustomUser.Role.ADMIN, is_staff=True
        )
        self.salesman = CustomUser.objects.create_user(
            email='sales@nit.edu', username='sales_u', password=self.password,
            role=CustomUser.Role.SALESMAN
        )
        self.production = CustomUser.objects.create_user(
            email='prod@nit.edu', username='prod_u', password=self.password,
            role=CustomUser.Role.PRODUCTION
        )
        self.auditor = CustomUser.objects.create_user(
            email='audit@nit.edu', username='audit_u', password=self.password,
            role=CustomUser.Role.AUDITOR
        )
        self.owner = CustomUser.objects.create_user(
            email='owner@nit.edu', username='owner_u', password=self.password,
            role=CustomUser.Role.OWNER
        )

    def test_admin_dashboard_contents(self):
        self.client.login(username='admin_u', password=self.password)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Administrator Command Center")
        self.assertContains(response, "Total Staff Accounts")
        self.assertContains(response, "Database Backend")

    def test_salesman_dashboard_contents(self):
        self.client.login(username='sales_u', password=self.password)
        response = self.client.get(reverse('salesman_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sales & Quotation Dashboard")
        self.assertContains(response, "Booked Pipeline Value")

    def test_production_dashboard_contents(self):
        self.client.login(username='prod_u', password=self.password)
        response = self.client.get(reverse('production_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Production Operations & Batch Control")
        self.assertContains(response, "Total Good Output")

    def test_auditor_dashboard_contents(self):
        self.client.login(username='audit_u', password=self.password)
        response = self.client.get(reverse('auditor_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Order-to-Audit Verification Suite")
        self.assertContains(response, "Total Audit Trail Events")

    def test_owner_dashboard_contents(self):
        self.client.login(username='owner_u', password=self.password)
        response = self.client.get(reverse('owner_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Executive Command Center")
        self.assertContains(response, "Total Invoiced Sales")


class OwnerDashboardBenchmarkCalculationsTests(TestCase):
    """
    Tests proving that Owner Dashboard figures are calculated accurately
    from live database records matching the exact NIT Trichy Benchmark.
    """

    def setUp(self):
        call_command('seed_snacks_benchmark')
        call_command('run_nit_production_benchmark')

        self.client = Client()
        self.password = 'OwnerPass123!'
        self.owner_user = CustomUser.objects.create_user(
            username='owner_bm_u',
            email='owner_benchmark@nit.edu',
            password=self.password,
            role=CustomUser.Role.OWNER
        )
        self.admin_user, _ = CustomUser.objects.get_or_create(
            username='admin_bm_u',
            defaults={
                'email': 'admin_bm@nit.edu',
                'role': CustomUser.Role.ADMIN,
                'is_staff': True
            }
        )
        self.salesman_user, _ = CustomUser.objects.get_or_create(
            username='sales_bm_u',
            defaults={
                'email': 'sales_bm@nit.edu',
                'role': CustomUser.Role.SALESMAN
            }
        )

        self.retailer_a, _ = Customer.objects.get_or_create(
            code='CUST-RETAIL-A-DASH',
            defaults={
                'name': 'Retailer A Supermarket Chennai',
                'customer_type': Customer.CustomerType.RETAILER,
                'state': 'Tamil Nadu',
                'city': 'Chennai',
                'billing_address': 'Anna Salai, Chennai, Tamil Nadu',
                'shipping_address': 'T. Nagar Hub, Chennai, Tamil Nadu',
                'tax_id_gst': '33AABCR1120K1ZX',
                'credit_days': 30
            }
        )
        self.sku = ProductPackSize.objects.get(sku_code='SKU-MRK-200G')
        self.uom_pcs = UnitOfMeasurement.objects.get(code='PCS')

        # Create Order & Invoice: 150 packets @ ₹50 = ₹7,500 + ₹187.50 CGST + ₹187.50 SGST = ₹7,875
        self.order = SalesOrder.objects.create(
            order_number=generate_sales_order_number(),
            customer=self.retailer_a,
            salesman=self.salesman_user,
            order_date=date.today(),
            status=SalesOrder.Status.APPROVED,
            delivery_state='Tamil Nadu',
            delivery_city='Chennai',
            is_interstate=False
        )
        SalesOrderItem.objects.create(
            sales_order=self.order,
            product_pack_size=self.sku,
            quantity=Decimal('150.00'),
            uom=self.uom_pcs,
            unit_price=Decimal('50.00')
        )
        self.order.update_totals()
        self.invoice = generate_invoice_for_order(self.order, user=self.admin_user)

        # Record partial remittance of ₹4,000 leaving ₹3,875 outstanding
        record_invoice_payment(
            invoice=self.invoice,
            amount=Decimal('4000.00'),
            payment_mode=PaymentRecord.Mode.UPI,
            transaction_reference='UPI-OWNER-TEST',
            user=self.admin_user
        )

    def test_owner_dashboard_exact_benchmark_figures(self):
        """
        Verifies Owner Dashboard aggregates:
        - Invoiced: ₹7,875.00 (Taxable: ₹7,500.00, Tax: ₹375.00)
        - Collected: ₹4,000.00
        - Outstanding: ₹3,875.00
        - Production output: 188 packets (Planned 200, yield 94.00%)
        - Yield variance alert present (-6.00%)
        - Flour closing: 120 kg, Oil closing: 19.5 L
        """
        self.client.login(username='owner_bm_u', password=self.password)
        res = self.client.get(reverse('owner_dashboard'))
        self.assertEqual(res.status_code, 200)

        ctx = res.context

        # Financials
        self.assertEqual(ctx['total_invoiced'], Decimal('7875.00'))
        self.assertEqual(ctx['total_taxable'], Decimal('7500.00'))
        self.assertEqual(ctx['total_tax'], Decimal('375.00'))
        self.assertEqual(ctx['total_collected'], Decimal('4000.00'))
        self.assertEqual(ctx['total_outstanding'], Decimal('3875.00'))

        # Production Output
        self.assertEqual(ctx['total_production_output'], Decimal('188.00'))
        self.assertEqual(ctx['total_planned_output'], Decimal('200.00'))
        self.assertEqual(ctx['completed_runs_count'], 1)
        self.assertEqual(ctx['overall_yield_pct'], Decimal('94.00'))

        # Yield Variance Alert
        self.assertEqual(len(ctx['yield_alert_runs']), 1)
        self.assertEqual(ctx['yield_alert_runs'][0].yield_variance_pct, Decimal('-6.00'))

        # Finished Goods on Hand
        # Murukku 200g: 50 opening + 188 produced = 238 packets on hand
        self.assertEqual(ctx['total_fg_packets'], Decimal('238.00'))

        # Raw Material Closing Balances
        flour_entry = next((rm for rm in ctx['raw_materials_summary'] if rm['code'] == 'RM-FLOUR'), None)
        self.assertIsNotNone(flour_entry)
        self.assertEqual(flour_entry['quantity'], Decimal('120.0000'))

        oil_entry = next((rm for rm in ctx['raw_materials_summary'] if rm['code'] == 'RM-OIL'), None)
        self.assertIsNotNone(oil_entry)
        self.assertEqual(oil_entry['quantity'], Decimal('19.5000'))
