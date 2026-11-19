from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.core.management import call_command
from django.core.exceptions import ValidationError

from apps.accounts.models import CustomUser
from apps.master_data.models import Customer, ProductPackSize, UnitOfMeasurement
from apps.inventory.models import StockItem, StockLedgerEntry, MovementType, ItemType
from .models import SalesOrder, SalesOrderItem, Invoice, Dispatch, PaymentRecord
from .services import (
    generate_sales_order_number,
    check_order_stock_availability,
    get_order_stock_shortage,
    approve_sales_order,
    reject_sales_order,
    generate_invoice_for_order,
    post_sales_dispatch,
    record_invoice_payment,
)
from .pdf_generator import generate_invoice_pdf


class ExactNITTrichySalesBenchmarkTests(TestCase):
    """
    Direct automated verification of the MANDATORY EXACT NIT Trichy Sales Benchmark:

    1. Retailer A — Tamil Nadu:
       - Order exactly 150 Murukku 200g packets.
       - Unit price Rs 50.
       - Taxable value Rs 7,500.
       - CGST Rs 187.50.
       - SGST Rs 187.50.
       - Invoice total Rs 7,875.
       - Dispatch exactly 150 packets.
       - Finished stock must decrease from 238 to 88 packets.

    2. Distributor B — Karnataka:
       - Order exactly 120 packets.
       - Available stock is 88 packets.
       - Shortage must be exactly 32 packets.
       - Approval/dispatch must not permit negative stock.
       - If an invoice is generated for the full order, taxable value must be Rs 6,000, IGST Rs 300, total Rs 6,300.

    Also verifies:
       - PDF contains the correct 150-packet invoice totals.
       - Duplicate invoice generation and dispatch are prevented.
       - Payment recording and outstanding calculations.
       - Seller GSTIN is clearly marked as demo/placeholder.
    """

    def setUp(self):
        call_command('seed_snacks_benchmark')
        call_command('run_nit_production_benchmark')

        self.admin_user = CustomUser.objects.create_user(
            email='admin_bench_sales@nit.edu',
            username='bench_admin_sales',
            password='AdminPass123!',
            role=CustomUser.Role.ADMIN
        )
        self.salesman_user = CustomUser.objects.create_user(
            email='salesman_bench_sales@nit.edu',
            username='bench_salesman_sales',
            password='SalesPass123!',
            role=CustomUser.Role.SALESMAN
        )
        self.auditor_user = CustomUser.objects.create_user(
            email='auditor_bench_sales@nit.edu',
            username='bench_auditor_sales',
            password='AuditPass123!',
            role=CustomUser.Role.AUDITOR
        )
        self.owner_user = CustomUser.objects.create_user(
            email='owner_bench_sales@nit.edu',
            username='bench_owner_sales',
            password='OwnerPass123!',
            role=CustomUser.Role.OWNER
        )

        self.sku = ProductPackSize.objects.get(sku_code='SKU-MRK-200G')
        self.uom_pcs = UnitOfMeasurement.objects.get(code='PCS')

        # Retailer A — Tamil Nadu
        self.retailer_a, _ = Customer.objects.get_or_create(
            code='CUST-RETAIL-A',
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

        # Distributor B — Karnataka
        self.distributor_b, _ = Customer.objects.get_or_create(
            code='CUST-DIST-B',
            defaults={
                'name': 'Distributor B Wholesale Bengaluru',
                'customer_type': Customer.CustomerType.DISTRIBUTOR,
                'state': 'Karnataka',
                'city': 'Bengaluru',
                'billing_address': 'Yeshwanthpur Industrial Suburb, Bengaluru, Karnataka',
                'shipping_address': 'Warehouse Complex 3, Bengaluru, Karnataka',
                'tax_id_gst': '29AABCD9910L1Z3',
                'credit_days': 45
            }
        )

    def test_baseline_finished_stock_is_238_packets(self):
        """Verifies opening 50 + produced 188 = 238 finished packets before sales."""
        total_finished = sum(
            s.quantity_on_hand for s in StockItem.objects.filter(
                product_pack_size=self.sku, quantity_on_hand__gt=0
            )
        )
        self.assertEqual(total_finished, Decimal('238.00'))

    def test_scenario_1_retailer_a_tamil_nadu_exact_benchmark(self):
        """
        Executes Scenario 1:
        - 150 packets @ Rs 50
        - Taxable value: Rs 7,500.00
        - CGST: Rs 187.50 (2.5%)
        - SGST: Rs 187.50 (2.5%)
        - Invoice Total: Rs 7,875.00
        - PDF contains all 150-packet figures
        - Dispatch: 150 packets
        - Stock decreases from 238 to 88 packets
        - Duplicate invoice and duplicate dispatch are prevented
        - Payment recording reconciles outstanding
        - Seller GSTIN marked as demo placeholder
        """
        # 1. Create Sales Order
        order_a = SalesOrder.objects.create(
            order_number='SO-TEST-RET-A',
            customer=self.retailer_a,
            salesman=self.salesman_user,
            order_date=date.today(),
            delivery_state='Tamil Nadu',
            delivery_city='Chennai',
            status=SalesOrder.Status.SUBMITTED
        )
        SalesOrderItem.objects.create(
            sales_order=order_a,
            product_pack_size=self.sku,
            quantity=Decimal('150.00'),
            uom=self.uom_pcs,
            unit_price=Decimal('50.00')
        )
        order_a.update_totals()
        order_a.refresh_from_db()

        # Check order valuations
        self.assertFalse(order_a.is_interstate)
        self.assertEqual(order_a.subtotal_amount, Decimal('7500.00'))
        self.assertEqual(order_a.cgst_amount, Decimal('187.50'))
        self.assertEqual(order_a.sgst_amount, Decimal('187.50'))
        self.assertEqual(order_a.igst_amount, Decimal('0.00'))
        self.assertEqual(order_a.total_tax_amount, Decimal('375.00'))
        self.assertEqual(order_a.total_amount, Decimal('7875.00'))

        # 2. Stock check before approval (238 on hand >= 150 required)
        is_avail, item, on_hand, req = check_order_stock_availability(order_a)
        self.assertTrue(is_avail)
        self.assertEqual(on_hand, Decimal('238.00'))
        self.assertEqual(req, Decimal('150.00'))
        self.assertEqual(order_a.get_stock_shortage(), Decimal('0.00'))

        # 3. Admin Approval
        approve_sales_order(order_a.pk, self.admin_user)
        order_a.refresh_from_db()
        self.assertEqual(order_a.status, SalesOrder.Status.APPROVED)
        self.assertEqual(order_a.approved_by, self.admin_user)

        # 4. Tax Invoice Generation
        inv_a = generate_invoice_for_order(order_a.pk, self.admin_user)
        self.assertEqual(inv_a.taxable_amount, Decimal('7500.00'))
        self.assertEqual(inv_a.cgst_amount, Decimal('187.50'))
        self.assertEqual(inv_a.sgst_amount, Decimal('187.50'))
        self.assertEqual(inv_a.igst_amount, Decimal('0.00'))
        self.assertEqual(inv_a.total_tax, Decimal('375.00'))
        self.assertEqual(inv_a.grand_total, Decimal('7875.00'))
        self.assertEqual(inv_a.payment_status, Invoice.PaymentStatus.PENDING)
        self.assertEqual(inv_a.balance_due, Decimal('7875.00'))

        # Check Seller GSTIN is clearly marked as demo/placeholder
        self.assertIn('Demo', inv_a.company_gstin)

        # 5. PDF generation and content stream verification
        pdf_bytes = generate_invoice_pdf(inv_a)
        self.assertTrue(pdf_bytes.startswith(b"%PDF-1.4"))
        self.assertTrue(b"%%EOF" in pdf_bytes)
        self.assertTrue(b"7500.00" in pdf_bytes)
        self.assertTrue(b"187.50" in pdf_bytes)
        self.assertTrue(b"7875.00" in pdf_bytes)
        self.assertTrue(b"150" in pdf_bytes)

        # 6. Duplicate Invoice Generation Prevention
        with self.assertRaises(ValidationError) as cm_inv:
            generate_invoice_for_order(order_a.pk, self.admin_user)
        self.assertIn("already been generated", str(cm_inv.exception))

        # 7. Dispatch exactly 150 packets
        disp_a = post_sales_dispatch(
            sales_order_id=order_a.pk,
            user=self.admin_user,
            carrier_name='Sri Murugan Roadways',
            vehicle_number='TN 45 AX 8810',
            lr_number='LR-BENCH-RET-A'
        )
        self.assertTrue(disp_a.is_posted)
        order_a.refresh_from_db()
        self.assertEqual(order_a.status, SalesOrder.Status.DISPATCHED)

        # Verify stock ledger entries sum to -150.00
        ledger_entries = StockLedgerEntry.objects.filter(
            product_pack_size=self.sku,
            movement_type=MovementType.SALES_DISPATCH,
            reference_id=disp_a.dispatch_number
        )
        self.assertTrue(ledger_entries.exists())
        total_deducted = sum(e.quantity_change for e in ledger_entries)
        self.assertEqual(total_deducted, Decimal('-150.00'))

        # Verify finished stock decreased from 238 to 88 packets
        stock_remaining = sum(
            s.quantity_on_hand for s in StockItem.objects.filter(
                product_pack_size=self.sku, quantity_on_hand__gt=0
            )
        )
        self.assertEqual(stock_remaining, Decimal('88.00'))

        # 8. Duplicate Dispatch Prevention
        with self.assertRaises(ValidationError) as cm_disp:
            post_sales_dispatch(order_a.pk, self.admin_user)
        self.assertIn("already been dispatched", str(cm_disp.exception))

        # 9. Payment Recording & Outstanding Calculations
        # Partial payment of Rs 4,000
        pay1 = record_invoice_payment(
            invoice_id=inv_a.pk,
            amount=Decimal('4000.00'),
            payment_mode=PaymentRecord.Mode.UPI,
            reference_no='UPI-TEST-001',
            user=self.admin_user
        )
        inv_a.refresh_from_db()
        self.assertEqual(inv_a.payment_status, Invoice.PaymentStatus.PARTIAL)
        self.assertEqual(inv_a.amount_paid, Decimal('4000.00'))
        self.assertEqual(inv_a.balance_due, Decimal('3875.00'))

        # Final payment of Rs 3,875
        pay2 = record_invoice_payment(
            invoice_id=inv_a.pk,
            amount=Decimal('3875.00'),
            payment_mode=PaymentRecord.Mode.NEFT_RTGS,
            reference_no='NEFT-TEST-002',
            user=self.admin_user
        )
        inv_a.refresh_from_db()
        self.assertEqual(inv_a.payment_status, Invoice.PaymentStatus.PAID)
        self.assertEqual(inv_a.amount_paid, Decimal('7875.00'))
        self.assertEqual(inv_a.balance_due, Decimal('0.00'))

    def test_scenario_2_distributor_b_karnataka_exact_benchmark(self):
        """
        Executes Scenario 2:
        - Prior state: 88 packets available on hand
        - Order: exactly 120 packets for Distributor B (Karnataka)
        - Shortage must be exactly 32 packets (120 - 88 = 32)
        - Approval/dispatch must NOT permit negative stock
        - Full order invoice: Taxable Rs 6,000, IGST Rs 300 (5%), Total Rs 6,300
        """
        # 1. First consume 150 packets to leave exactly 88 packets on hand
        # Opening is 238. Deduct 150.
        stock_item = StockItem.objects.filter(product_pack_size=self.sku, quantity_on_hand__gt=0).first()
        initial_stock = sum(s.quantity_on_hand for s in StockItem.objects.filter(product_pack_size=self.sku, quantity_on_hand__gt=0))
        self.assertEqual(initial_stock, Decimal('238.00'))

        # Deduct 150 to set stock to 88
        stock_item.quantity_on_hand -= Decimal('150.00')
        stock_item.save(update_fields=['quantity_on_hand'])
        avail_stock = sum(s.quantity_on_hand for s in StockItem.objects.filter(product_pack_size=self.sku, quantity_on_hand__gt=0))
        self.assertEqual(avail_stock, Decimal('88.00'))

        # 2. Distributor B orders exactly 120 packets
        order_b = SalesOrder.objects.create(
            order_number='SO-TEST-DIST-B',
            customer=self.distributor_b,
            salesman=self.salesman_user,
            order_date=date.today(),
            delivery_state='Karnataka',
            delivery_city='Bengaluru',
            status=SalesOrder.Status.SUBMITTED
        )
        SalesOrderItem.objects.create(
            sales_order=order_b,
            product_pack_size=self.sku,
            quantity=Decimal('120.00'),
            uom=self.uom_pcs,
            unit_price=Decimal('50.00')
        )
        order_b.update_totals()
        order_b.refresh_from_db()

        # 3. Verify Shortage is EXACTLY 32 packets
        shortage_qty, is_short, on_hand, req = get_order_stock_shortage(order_b)
        order_shortage = order_b.get_stock_shortage()
        self.assertTrue(is_short)
        self.assertEqual(on_hand, Decimal('88.00'))
        self.assertEqual(req, Decimal('120.00'))
        self.assertEqual(shortage_qty, Decimal('32.00'))
        self.assertEqual(order_shortage, Decimal('32.00'))

        # 4. Approval must strictly prevent negative stock
        with self.assertRaises(ValidationError) as cm_app:
            approve_sales_order(order_b.pk, self.admin_user)
        self.assertIn("Insufficient finished goods stock", str(cm_app.exception))
        self.assertIn("Shortage: 32.00", str(cm_app.exception))
        self.assertIn("Negative inventory is strictly prohibited", str(cm_app.exception))

        # 5. Dispatch must strictly prevent negative stock
        with self.assertRaises(ValidationError) as cm_disp:
            post_sales_dispatch(order_b.pk, self.admin_user)
        self.assertIn("Must be in APPROVED or INVOICED status", str(cm_disp.exception))

        # 6. Verify Full Order Invoice Totals (Inter-state Karnataka):
        # Taxable: Rs 6,000, IGST: Rs 300, Total: Rs 6,300
        inv_b = generate_invoice_for_order(order_b.pk, self.admin_user, allow_unapproved=True)
        self.assertTrue(inv_b.is_interstate)
        self.assertEqual(inv_b.taxable_amount, Decimal('6000.00'))
        self.assertEqual(inv_b.cgst_amount, Decimal('0.00'))
        self.assertEqual(inv_b.sgst_amount, Decimal('0.00'))
        self.assertEqual(inv_b.igst_rate_pct, Decimal('5.00'))
        self.assertEqual(inv_b.igst_amount, Decimal('300.00'))
        self.assertEqual(inv_b.total_tax, Decimal('300.00'))
        self.assertEqual(inv_b.grand_total, Decimal('6300.00'))


class SalesRolePermissionsTests(TestCase):
    """
    Automated verification of role-based permissions:
    - Salesman: create, edit draft, submit. Forbidden from approve, reject, dispatch.
    - Admin: verify, approve, reject, dispatch, invoice, record payments.
    - Auditor / Accountant: read-only access (dashboard, order list, order detail,
      invoice list, invoice detail, PDF download, dispatch list). Forbidden from
      creating orders, approving, rejecting, dispatching, or recording payments.
    - Owner: executive overview across dashboard, orders, invoices, dispatches.
    """

    def setUp(self):
        call_command('seed_snacks_benchmark')

        self.admin_user = CustomUser.objects.create_user(
            email='perm_admin@nit.edu', username='perm_admin', password='Pass!', role=CustomUser.Role.ADMIN
        )
        self.salesman_user = CustomUser.objects.create_user(
            email='perm_salesman@nit.edu', username='perm_salesman', password='Pass!', role=CustomUser.Role.SALESMAN
        )
        self.auditor_user = CustomUser.objects.create_user(
            email='perm_auditor@nit.edu', username='perm_auditor', password='Pass!', role=CustomUser.Role.AUDITOR
        )
        self.owner_user = CustomUser.objects.create_user(
            email='perm_owner@nit.edu', username='perm_owner', password='Pass!', role=CustomUser.Role.OWNER
        )

        self.client_salesman = Client()
        self.client_salesman.login(username='perm_salesman', password='Pass!')

        self.client_admin = Client()
        self.client_admin.login(username='perm_admin', password='Pass!')

        self.client_auditor = Client()
        self.client_auditor.login(username='perm_auditor', password='Pass!')

        self.client_owner = Client()
        self.client_owner.login(username='perm_owner', password='Pass!')

        self.customer = Customer.objects.get(code='CUST-SNK-01')
        self.sku = ProductPackSize.objects.get(sku_code='SKU-MRK-200G')
        self.uom_pcs = UnitOfMeasurement.objects.get(code='PCS')

    def test_salesman_permissions(self):
        """Salesman can create orders, but cannot approve, reject, or dispatch."""
        # Can access order create view
        resp = self.client_salesman.get(reverse('sales_order_create'))
        self.assertEqual(resp.status_code, 200)

        # Create draft order
        order = SalesOrder.objects.create(
            order_number='SO-PERM-SALES-1',
            customer=self.customer,
            salesman=self.salesman_user,
            status=SalesOrder.Status.SUBMITTED
        )

        # Salesman cannot approve order (403 Forbidden)
        resp_app = self.client_salesman.post(reverse('sales_order_approve', kwargs={'pk': order.pk}))
        self.assertEqual(resp_app.status_code, 403)

        # Salesman cannot reject order (403 Forbidden)
        resp_rej = self.client_salesman.post(reverse('sales_order_reject', kwargs={'pk': order.pk}))
        self.assertEqual(resp_rej.status_code, 403)

        # Salesman cannot access dispatch create (403 Forbidden)
        resp_disp = self.client_salesman.get(reverse('dispatch_create', kwargs={'order_pk': order.pk}))
        self.assertEqual(resp_disp.status_code, 403)

    def test_admin_permissions(self):
        """Admin has approval, rejection, and dispatch capabilities."""
        order = SalesOrder.objects.create(
            order_number='SO-PERM-ADM-1',
            customer=self.customer,
            salesman=self.salesman_user,
            status=SalesOrder.Status.SUBMITTED
        )
        SalesOrderItem.objects.create(
            sales_order=order,
            product_pack_size=self.sku,
            quantity=Decimal('10.00'),
            uom=self.uom_pcs,
            unit_price=Decimal('50.00')
        )
        order.update_totals()

        # Admin can approve
        resp_app = self.client_admin.post(reverse('sales_order_approve', kwargs={'pk': order.pk}))
        self.assertEqual(resp_app.status_code, 302)  # Redirects to detail on success
        order.refresh_from_db()
        self.assertEqual(order.status, SalesOrder.Status.APPROVED)

    def test_auditor_accountant_read_only_permissions(self):
        """
        Auditor has complete read-only visibility for compliance inspection,
        but cannot create, approve, reject, dispatch, or record payments.
        """
        order = SalesOrder.objects.create(
            order_number='SO-PERM-AUD-1',
            customer=self.customer,
            salesman=self.salesman_user,
            status=SalesOrder.Status.APPROVED
        )
        SalesOrderItem.objects.create(
            sales_order=order,
            product_pack_size=self.sku,
            quantity=Decimal('10.00'),
            uom=self.uom_pcs,
            unit_price=Decimal('50.00')
        )
        order.update_totals()
        invoice = generate_invoice_for_order(order.pk, self.admin_user)

        # 1. Auditor can view dashboard, lists, and details (Read-Only 200 OK)
        self.assertEqual(self.client_auditor.get(reverse('sales_hub')).status_code, 200)
        self.assertEqual(self.client_auditor.get(reverse('sales_order_list')).status_code, 200)
        self.assertEqual(self.client_auditor.get(reverse('sales_order_detail', kwargs={'pk': order.pk})).status_code, 200)
        self.assertEqual(self.client_auditor.get(reverse('invoice_list')).status_code, 200)
        self.assertEqual(self.client_auditor.get(reverse('invoice_detail', kwargs={'pk': invoice.pk})).status_code, 200)
        self.assertEqual(self.client_auditor.get(reverse('invoice_pdf', kwargs={'pk': invoice.pk})).status_code, 200)
        self.assertEqual(self.client_auditor.get(reverse('dispatch_list')).status_code, 200)

        # 2. Auditor is strictly blocked from write actions (403 Forbidden)
        self.assertEqual(self.client_auditor.get(reverse('sales_order_create')).status_code, 403)
        self.assertEqual(self.client_auditor.post(reverse('sales_order_approve', kwargs={'pk': order.pk})).status_code, 403)
        self.assertEqual(self.client_auditor.post(reverse('sales_order_reject', kwargs={'pk': order.pk})).status_code, 403)
        self.assertEqual(self.client_auditor.get(reverse('dispatch_create', kwargs={'order_pk': order.pk})).status_code, 403)
        self.assertEqual(self.client_auditor.post(reverse('payment_create', kwargs={'invoice_pk': invoice.pk})).status_code, 403)

    def test_owner_permissions(self):
        """Owner can view commercial hub, orders, invoices, and dispatches."""
        self.assertEqual(self.client_owner.get(reverse('sales_hub')).status_code, 200)
        self.assertEqual(self.client_owner.get(reverse('sales_order_list')).status_code, 200)
        self.assertEqual(self.client_owner.get(reverse('sales_order_create')).status_code, 200)
        self.assertEqual(self.client_owner.get(reverse('invoice_list')).status_code, 200)
        self.assertEqual(self.client_owner.get(reverse('dispatch_list')).status_code, 200)
