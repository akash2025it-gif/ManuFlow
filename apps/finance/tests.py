from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.core.management import call_command
from django.core.exceptions import ValidationError

from apps.accounts.models import CustomUser
from apps.master_data.models import Customer, ProductPackSize, UnitOfMeasurement
from apps.inventory.models import StockItem, StockLedgerEntry, MovementType
from apps.production.models import ProductionRun
from apps.sales.models import SalesOrder, SalesOrderItem, Invoice, PaymentRecord
from apps.sales.services import (
    generate_sales_order_number,
    generate_invoice_for_order,
    post_sales_dispatch,
    record_invoice_payment,
)
from apps.finance.services import (
    get_receivables_summary,
    get_customer_receivables_summary,
    get_overdue_invoices,
    get_sales_register,
    get_monthly_gst_summary,
    get_current_stock_report,
    get_stock_movement_report,
    get_production_variance_report,
    get_sales_dispatch_report,
)


class FinanceModuleTests(TestCase):
    def setUp(self):
        call_command('seed_snacks_benchmark')
        call_command('run_nit_production_benchmark')

        # Create distinct users for all roles
        self.accountant_user = CustomUser.objects.create_user(
            username='fin_acc_user',
            email='accountant_fin@nit.edu',
            password='TestPassword123!',
            role=CustomUser.Role.ACCOUNTANT
        )
        self.auditor_user = CustomUser.objects.create_user(
            username='fin_aud_user',
            email='auditor_fin@nit.edu',
            password='TestPassword123!',
            role=CustomUser.Role.AUDITOR
        )
        self.admin_user = CustomUser.objects.create_user(
            username='fin_adm_user',
            email='admin_fin@nit.edu',
            password='TestPassword123!',
            role=CustomUser.Role.ADMIN
        )
        self.owner_user = CustomUser.objects.create_user(
            username='fin_own_user',
            email='owner_fin@nit.edu',
            password='TestPassword123!',
            role=CustomUser.Role.OWNER
        )
        self.salesman_user = CustomUser.objects.create_user(
            username='fin_sal_user',
            email='salesman_fin@nit.edu',
            password='TestPassword123!',
            role=CustomUser.Role.SALESMAN
        )
        self.production_user = CustomUser.objects.create_user(
            username='fin_prd_user',
            email='production_fin@nit.edu',
            password='TestPassword123!',
            role=CustomUser.Role.PRODUCTION
        )

        self.sku = ProductPackSize.objects.get(sku_code='SKU-MRK-200G')
        self.uom_pcs = UnitOfMeasurement.objects.get(code='PCS')

        # Retailer A — Tamil Nadu (Intra-state: 2.5% CGST + 2.5% SGST)
        self.retailer_a, _ = Customer.objects.get_or_create(
            code='CUST-RETAIL-A-FIN',
            defaults={
                'name': 'Retailer A Supermarket Chennai',
                'customer_type': Customer.CustomerType.RETAILER,
                'state': 'Tamil Nadu',
                'city': 'Chennai',
                'billing_address': 'Anna Salai, Chennai, Tamil Nadu',
                'shipping_address': 'T. Nagar Hub, Chennai, Tamil Nadu',
                'tax_id_gst': '33AABCR1120K1ZX',
                'credit_days': 15,
                'credit_limit': Decimal('50000.00'),
            }
        )

        # Distributor B — Karnataka (Inter-state: 5% IGST)
        self.distributor_b, _ = Customer.objects.get_or_create(
            code='CUST-DIST-B-FIN',
            defaults={
                'name': 'Distributor B Wholesale Bengaluru',
                'customer_type': Customer.CustomerType.DISTRIBUTOR,
                'state': 'Karnataka',
                'city': 'Bengaluru',
                'billing_address': 'Yeshwanthpur Industrial Suburb, Bengaluru, Karnataka',
                'shipping_address': 'Warehouse Complex 3, Bengaluru, Karnataka',
                'tax_id_gst': '29AABCD9910L1Z3',
                'credit_days': 30,
                'credit_limit': Decimal('100000.00'),
            }
        )

        # Create Order & Invoice 1: Intra-state Tamil Nadu (150 packets @ ₹50 = ₹7,500 + ₹187.50 CGST + ₹187.50 SGST = ₹7,875)
        self.order_tn = SalesOrder.objects.create(
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
            sales_order=self.order_tn,
            product_pack_size=self.sku,
            quantity=Decimal('150.00'),
            uom=self.uom_pcs,
            unit_price=Decimal('50.00')
        )
        self.order_tn.update_totals()
        self.invoice_tn = generate_invoice_for_order(self.order_tn, user=self.admin_user)

        # Create Order & Invoice 2: Inter-state Karnataka (50 packets @ ₹50 = ₹2,500 + 5% IGST ₹125 = ₹2,625)
        # Made overdue for overdue receivables testing
        self.order_ka = SalesOrder.objects.create(
            order_number=generate_sales_order_number(),
            customer=self.distributor_b,
            salesman=self.salesman_user,
            order_date=date.today() - timedelta(days=40),
            status=SalesOrder.Status.APPROVED,
            delivery_state='Karnataka',
            delivery_city='Bengaluru',
            is_interstate=True
        )
        SalesOrderItem.objects.create(
            sales_order=self.order_ka,
            product_pack_size=self.sku,
            quantity=Decimal('50.00'),
            uom=self.uom_pcs,
            unit_price=Decimal('50.00')
        )
        self.order_ka.update_totals()
        self.invoice_ka = generate_invoice_for_order(self.order_ka, user=self.admin_user)
        self.invoice_ka.invoice_date = date.today() - timedelta(days=40)
        self.invoice_ka.due_date = date.today() - timedelta(days=10)
        self.invoice_ka.save(update_fields=['invoice_date', 'due_date'])

        self.client = Client()

    # ==================================================================
    # 1. PAYMENT MANAGEMENT & OVERPAYMENT RESTRICTIONS
    # ==================================================================

    def test_record_partial_payment_updates_balance(self):
        """Test partial payment updates amount_paid, balance_due, and transitions to PARTIAL."""
        # Invoice TN total = ₹7,875.00. Payment of ₹4,000 leaves ₹3,875 outstanding.
        payment = record_invoice_payment(
            invoice=self.invoice_tn,
            amount=Decimal('4000.00'),
            payment_mode=PaymentRecord.Mode.UPI,
            transaction_reference='UPI-TXN-998877',
            recorded_by=self.accountant_user,
            notes='Advance partial remittance'
        )
        self.invoice_tn.refresh_from_db()
        self.assertEqual(payment.amount, Decimal('4000.00'))
        self.assertEqual(self.invoice_tn.amount_paid, Decimal('4000.00'))
        self.assertEqual(self.invoice_tn.balance_due, Decimal('3875.00'))
        self.assertEqual(self.invoice_tn.payment_status, Invoice.PaymentStatus.PARTIAL)

    def test_record_full_payment_settlement(self):
        """Test full payment sets balance_due to 0 and transitions to PAID."""
        # Invoice KA total = ₹2,625.00
        payment = record_invoice_payment(
            invoice=self.invoice_ka,
            amount=Decimal('2625.00'),
            payment_mode=PaymentRecord.Mode.NEFT,
            transaction_reference='NEFT-UTR-112233',
            recorded_by=self.accountant_user,
            notes='Full invoice clearance'
        )
        self.invoice_ka.refresh_from_db()
        self.assertEqual(self.invoice_ka.amount_paid, Decimal('2625.00'))
        self.assertEqual(self.invoice_ka.balance_due, Decimal('0.00'))
        self.assertEqual(self.invoice_ka.payment_status, Invoice.PaymentStatus.PAID)

    def test_prevent_payment_exceeding_invoice_balance(self):
        """Test that payment amount > balance due raises ValidationError and rolls back."""
        # Invoice TN balance = ₹7,875.00. Attempting ₹8,000.00 must raise ValidationError.
        with self.assertRaises(ValidationError) as ctx:
            record_invoice_payment(
                invoice=self.invoice_tn,
                amount=Decimal('8000.00'),
                payment_mode=PaymentRecord.Mode.CASH,
                recorded_by=self.accountant_user
            )
        self.assertIn("exceeds invoice outstanding balance", str(ctx.exception))

        # Verify transaction rollback: invoice balance unchanged and no payment record persisted
        self.invoice_tn.refresh_from_db()
        self.assertEqual(self.invoice_tn.amount_paid, Decimal('0.00'))
        self.assertEqual(self.invoice_tn.balance_due, Decimal('7875.00'))
        self.assertEqual(self.invoice_tn.payment_status, Invoice.PaymentStatus.PENDING)
        self.assertEqual(PaymentRecord.objects.filter(invoice=self.invoice_tn).count(), 0)

    def test_prevent_payment_on_fully_paid_invoice(self):
        """Test that paying an already settled invoice raises ValidationError."""
        record_invoice_payment(
            invoice=self.invoice_ka,
            amount=Decimal('2625.00'),
            payment_mode=PaymentRecord.Mode.RTGS,
            recorded_by=self.accountant_user
        )
        self.invoice_ka.refresh_from_db()
        self.assertEqual(self.invoice_ka.payment_status, Invoice.PaymentStatus.PAID)

        with self.assertRaises(ValidationError) as ctx:
            record_invoice_payment(
                invoice=self.invoice_ka,
                amount=Decimal('100.00'),
                payment_mode=PaymentRecord.Mode.CHEQUE,
                recorded_by=self.accountant_user
            )
        self.assertIn("already fully settled", str(ctx.exception))

    def test_payment_modes_enumeration(self):
        """Verify explicit support for UPI, CASH, NEFT, RTGS, and CHEQUE."""
        supported = [c[0] for c in PaymentRecord.Mode.choices]
        for mode in ['UPI', 'CASH', 'NEFT', 'RTGS', 'CHEQUE']:
            self.assertIn(mode, supported)

    # ==================================================================
    # 2. RECEIVABLES & AGING CALCULATIONS
    # ==================================================================

    def test_receivables_summary_kpis(self):
        """Verify system receivables totals: Invoiced = 7875 + 2625 = 10500."""
        kpis = get_receivables_summary()
        self.assertEqual(kpis['total_invoiced'], Decimal('10500.00'))
        self.assertEqual(kpis['total_received'], Decimal('0.00'))
        self.assertEqual(kpis['total_outstanding'], Decimal('10500.00'))
        self.assertEqual(kpis['total_invoices_count'], 2)
        # Invoice KA is past due
        self.assertEqual(kpis['overdue_count'], 1)
        self.assertEqual(kpis['overdue_amount'], Decimal('2625.00'))

    def test_customer_receivables_breakdown(self):
        """Verify customer-wise outstanding grouping and overdue counts."""
        cust_summaries = get_customer_receivables_summary()
        self.assertEqual(len(cust_summaries), 2)
        top = cust_summaries[0]
        self.assertEqual(top['customer'].name, 'Retailer A Supermarket Chennai')
        self.assertEqual(top['total_outstanding'], Decimal('7875.00'))

        second = cust_summaries[1]
        self.assertEqual(second['customer'].name, 'Distributor B Wholesale Bengaluru')
        self.assertEqual(second['total_outstanding'], Decimal('2625.00'))
        self.assertEqual(second['overdue_count'], 1)
        self.assertEqual(second['overdue_amount'], Decimal('2625.00'))

    def test_overdue_invoices_query(self):
        """Verify overdue invoices query matches due_date < today."""
        overdue = get_overdue_invoices()
        self.assertEqual(len(overdue), 1)
        self.assertEqual(overdue[0].invoice_number, self.invoice_ka.invoice_number)

    # ==================================================================
    # 3. GST REPORTS (INTRA VS INTER)
    # ==================================================================

    def test_gst_sales_register_breakup(self):
        """
        Verify GST sales register distinguishes:
        - Intra-state (Tamil Nadu): 2.5% CGST (₹187.50) + 2.5% SGST (₹187.50)
        - Inter-state (Karnataka): 5% IGST (₹125.00)
        - Taxable turnover: ₹7,500 + ₹2,500 = ₹10,000.00
        """
        invoices, summary = get_sales_register()
        self.assertEqual(summary['total_count'], 2)
        self.assertEqual(summary['intra_count'], 1)
        self.assertEqual(summary['inter_count'], 1)
        self.assertEqual(summary['total_taxable'], Decimal('10000.00'))
        self.assertEqual(summary['total_cgst'], Decimal('187.50'))
        self.assertEqual(summary['total_sgst'], Decimal('187.50'))
        self.assertEqual(summary['total_igst'], Decimal('125.00'))
        self.assertEqual(summary['total_tax'], Decimal('500.00'))
        self.assertEqual(summary['grand_total'], Decimal('10500.00'))

    def test_gst_sales_register_filtering(self):
        """Verify filtering sales register by jurisdiction."""
        intra_invs, intra_sum = get_sales_register(state_filter='INTRA')
        self.assertEqual(intra_sum['total_count'], 1)
        self.assertEqual(intra_sum['total_taxable'], Decimal('7500.00'))
        self.assertEqual(intra_sum['total_cgst'], Decimal('187.50'))
        self.assertEqual(intra_sum['total_sgst'], Decimal('187.50'))
        self.assertEqual(intra_sum['total_igst'], Decimal('0.00'))

        inter_invs, inter_sum = get_sales_register(state_filter='INTER')
        self.assertEqual(inter_sum['total_count'], 1)
        self.assertEqual(inter_sum['total_taxable'], Decimal('2500.00'))
        self.assertEqual(inter_sum['total_cgst'], Decimal('0.00'))
        self.assertEqual(inter_sum['total_sgst'], Decimal('0.00'))
        self.assertEqual(inter_sum['total_igst'], Decimal('125.00'))

    def test_monthly_gst_summary_totals(self):
        """Verify monthly aggregation rollups for the calendar year."""
        year = date.today().year
        months_data, year_totals = get_monthly_gst_summary(year)
        self.assertEqual(len(months_data), 12)
        self.assertEqual(year_totals['taxable_amount'], Decimal('10000.00'))
        self.assertEqual(year_totals['total_tax'], Decimal('500.00'))
        self.assertEqual(year_totals['grand_total'], Decimal('10500.00'))

    # ==================================================================
    # 4. STOCK & PRODUCTION REPORTS
    # ==================================================================

    def test_current_stock_report_reflects_benchmark(self):
        """Verify stock report accurately reflects benchmark inventory balances."""
        report = get_current_stock_report()
        # Finished Murukku total across batches is 238 pkts (50 opening + 188 produced)
        fg_items = [i for i in report['finished_goods'] if i['code'] == 'SKU-MRK-200G']
        total_fg_qty = sum(i['quantity_on_hand'] for i in fg_items)
        self.assertEqual(total_fg_qty, Decimal('238.00'))

        # Raw flour closing across batches is 120 kg (60 remaining in opening + 60 purchased)
        flour_items = [i for i in report['raw_materials'] if 'Flour' in i['name']]
        total_flour_qty = sum(i['quantity_on_hand'] for i in flour_items)
        self.assertEqual(total_flour_qty, Decimal('120.00'))

        # Oil closing is 19.5 L
        oil_items = [i for i in report['raw_materials'] if 'Oil' in i['name']]
        total_oil_qty = sum(i['quantity_on_hand'] for i in oil_items)
        self.assertEqual(total_oil_qty, Decimal('19.50'))

    def test_stock_movement_ledger_traceability(self):
        """Verify stock movement ledger report tracks historical movements."""
        ledger = get_stock_movement_report()
        self.assertTrue(len(ledger) > 0)
        movement_types = set(e.movement_type for e in ledger)
        self.assertIn(MovementType.OPENING_BALANCE, movement_types)
        self.assertIn(MovementType.PRODUCTION_CONSUMPTION, movement_types)
        self.assertIn(MovementType.PRODUCTION_RECEIPT, movement_types)

    def test_production_variance_report_calculations(self):
        """Verify production report contains exact benchmark yield variance and costing."""
        runs = get_production_variance_report()
        self.assertEqual(len(runs), 1)
        run = runs[0]
        # Benchmark run: planned 200, actual 188 -> yield variance -6.00%
        self.assertEqual(run.planned_quantity, Decimal('200.00'))
        self.assertEqual(run.actual_output_quantity, Decimal('188.00'))
        self.assertEqual(run.yield_variance_pct, Decimal('-6.00'))
        self.assertTrue(run.is_yield_alert_triggered)  # deviation >= 3%
        # Total cost Rs 5,855.00 / 188 pkts = Rs 31.14
        self.assertEqual(run.total_production_cost, Decimal('5855.00'))
        self.assertEqual(run.unit_cost_per_output.quantize(Decimal('0.01')), Decimal('31.14'))

    # ==================================================================
    # 5. DATA EXPORTS (CSV & EXCEL)
    # ==================================================================

    def test_export_sales_register_csv_and_excel(self):
        """Verify CSV and Excel exports of GST sales register."""
        self.client.force_login(self.accountant_user)

        # CSV Export
        res_csv = self.client.get(reverse('finance:export_sales_register') + '?format=csv')
        self.assertEqual(res_csv.status_code, 200)
        self.assertEqual(res_csv['Content-Type'], 'text/csv; charset=utf-8')
        content_csv = res_csv.content.decode('utf-8-sig')
        self.assertTrue(content_csv.startswith('Invoice #,Invoice Date'))
        self.assertIn(self.invoice_tn.invoice_number, content_csv)
        self.assertIn('7875.00', content_csv)

        # Excel Export
        res_xls = self.client.get(reverse('finance:export_sales_register') + '?format=excel')
        self.assertEqual(res_xls.status_code, 200)
        self.assertEqual(res_xls['Content-Type'], 'application/vnd.ms-excel')
        content_xls = res_xls.content.decode('utf-8')
        self.assertIn('<?xml version="1.0" encoding="UTF-8"?>', content_xls)
        self.assertIn('Sales Register', content_xls)
        self.assertIn(self.invoice_tn.invoice_number, content_xls)

    def test_export_receivables_csv_and_excel(self):
        """Verify CSV and Excel exports of receivables summary."""
        self.client.force_login(self.accountant_user)

        # CSV
        res_csv = self.client.get(reverse('finance:export_receivables') + '?format=csv')
        self.assertEqual(res_csv.status_code, 200)
        content_csv = res_csv.content.decode('utf-8-sig')
        self.assertIn('Customer Code,Customer Name', content_csv)
        self.assertIn('Retailer A Supermarket Chennai', content_csv)
        self.assertIn('7875.00', content_csv)

        # Excel
        res_xls = self.client.get(reverse('finance:export_receivables') + '?format=excel')
        self.assertEqual(res_xls.status_code, 200)
        content_xls = res_xls.content.decode('utf-8')
        self.assertIn('Receivables', content_xls)
        self.assertIn('Distributor B Wholesale Bengaluru', content_xls)

    def test_export_stock_summary_and_ledger(self):
        """Verify stock summary and ledger exports."""
        self.client.force_login(self.accountant_user)

        res_stock = self.client.get(reverse('finance:export_stock_summary') + '?format=csv')
        self.assertEqual(res_stock.status_code, 200)
        self.assertIn('Murukku', res_stock.content.decode('utf-8-sig'))

        res_ledger = self.client.get(reverse('finance:export_stock_ledger') + '?format=csv')
        self.assertEqual(res_ledger.status_code, 200)
        self.assertIn('Movement Type', res_ledger.content.decode('utf-8-sig'))

    # ==================================================================
    # 6. ROLE PERMISSIONS MATRIX (RBAC)
    # ==================================================================

    def test_accountant_can_manage_payments(self):
        """Accountant can view financial dashboards and record payments."""
        self.client.force_login(self.accountant_user)

        self.assertEqual(self.client.get(reverse('finance:dashboard')).status_code, 200)
        self.assertEqual(self.client.get(reverse('finance:payments_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('finance:payment_create')).status_code, 200)

        # Post payment via view
        post_data = {
            'invoice': self.invoice_tn.id,
            'payment_date': date.today().strftime('%Y-%m-%d'),
            'amount': '2500.00',
            'payment_mode': PaymentRecord.Mode.UPI,
            'transaction_reference': 'UPI-TEST-RBAC',
            'notes': 'Accountant posting test'
        }
        res_post = self.client.post(reverse('finance:payment_create'), post_data)
        self.assertEqual(res_post.status_code, 302)
        self.invoice_tn.refresh_from_db()
        self.assertEqual(self.invoice_tn.amount_paid, Decimal('2500.00'))

    def test_auditor_has_readonly_access_and_cannot_record_payment(self):
        """Auditor can view all financial and stock reports but cannot record payments (HTTP 403)."""
        self.client.force_login(self.auditor_user)

        # Read-only reports access
        self.assertEqual(self.client.get(reverse('finance:dashboard')).status_code, 200)
        self.assertEqual(self.client.get(reverse('finance:receivables_summary')).status_code, 200)
        self.assertEqual(self.client.get(reverse('finance:payments_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('finance:gst_sales_register')).status_code, 200)
        self.assertEqual(self.client.get(reverse('finance:gst_monthly_summary')).status_code, 200)
        self.assertEqual(self.client.get(reverse('finance:stock_report')).status_code, 200)
        self.assertEqual(self.client.get(reverse('finance:stock_ledger_report')).status_code, 200)
        self.assertEqual(self.client.get(reverse('finance:production_variance_report')).status_code, 200)
        self.assertEqual(self.client.get(reverse('finance:sales_dispatch_report')).status_code, 200)

        # Payment recording blocked (HTTP 403)
        self.assertEqual(self.client.get(reverse('finance:payment_create')).status_code, 403)
        self.assertEqual(self.client.post(reverse('finance:payment_create'), {'amount': '100'}).status_code, 403)

    def test_salesman_access_restrictions(self):
        """Salesman can view sales register and dispatches, blocked from payments and stock."""
        self.client.force_login(self.salesman_user)

        # Permitted
        self.assertEqual(self.client.get(reverse('finance:gst_sales_register')).status_code, 200)
        self.assertEqual(self.client.get(reverse('finance:sales_dispatch_report')).status_code, 200)

        # Blocked (HTTP 403)
        self.assertEqual(self.client.get(reverse('finance:payment_create')).status_code, 403)
        self.assertEqual(self.client.get(reverse('finance:stock_report')).status_code, 403)
        self.assertEqual(self.client.get(reverse('finance:stock_ledger_report')).status_code, 403)

    def test_production_access_restrictions(self):
        """Production supervisor can view stock & production variance, blocked from sales & payments."""
        self.client.force_login(self.production_user)

        # Permitted
        self.assertEqual(self.client.get(reverse('finance:stock_report')).status_code, 200)
        self.assertEqual(self.client.get(reverse('finance:stock_ledger_report')).status_code, 200)
        self.assertEqual(self.client.get(reverse('finance:production_variance_report')).status_code, 200)

        # Blocked (HTTP 403)
        self.assertEqual(self.client.get(reverse('finance:payment_create')).status_code, 403)
        self.assertEqual(self.client.get(reverse('finance:gst_sales_register')).status_code, 403)

    def test_owner_and_admin_full_access(self):
        """Owner and Admin have full access across all endpoints."""
        for user in [self.owner_user, self.admin_user]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('finance:dashboard')).status_code, 200)
            self.assertEqual(self.client.get(reverse('finance:receivables_summary')).status_code, 200)
            self.assertEqual(self.client.get(reverse('finance:payments_list')).status_code, 200)
            self.assertEqual(self.client.get(reverse('finance:payment_create')).status_code, 200)
            self.assertEqual(self.client.get(reverse('finance:gst_sales_register')).status_code, 200)
            self.assertEqual(self.client.get(reverse('finance:stock_report')).status_code, 200)
            self.assertEqual(self.client.get(reverse('finance:export_sales_register')).status_code, 200)
