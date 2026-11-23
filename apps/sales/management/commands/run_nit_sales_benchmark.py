from decimal import Decimal
from datetime import date
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.accounts.models import CustomUser
from apps.accounts.utils import get_or_create_demo_user
from apps.master_data.models import Customer, ProductPackSize, UnitOfMeasurement
from apps.inventory.models import StockItem, StockLedgerEntry, MovementType
from apps.sales.models import SalesOrder, SalesOrderItem, Invoice, Dispatch, PaymentRecord
from apps.sales.services import (
    generate_sales_order_number,
    check_order_stock_availability,
    get_order_stock_shortage,
    approve_sales_order,
    generate_invoice_for_order,
    post_sales_dispatch,
    record_invoice_payment,
)
from apps.sales.pdf_generator import generate_invoice_pdf


class Command(BaseCommand):
    help = (
        'Executes and verifies the exact NIT Trichy Sales Management Benchmark:\n'
        '1. Retailer A — Tamil Nadu:\n'
        '   - Order: 150 Murukku 200g packets @ Rs 50/unit\n'
        '   - Taxable value: Rs 7,500.00\n'
        '   - CGST: Rs 187.50 (2.5%), SGST: Rs 187.50 (2.5%)\n'
        '   - Invoice total: Rs 7,875.00\n'
        '   - Dispatch: exactly 150 packets\n'
        '   - Finished stock decreases from 238 to 88 packets\n'
        '2. Distributor B — Karnataka:\n'
        '   - Order: 120 packets\n'
        '   - Available stock: 88 packets\n'
        '   - Shortage: exactly 32 packets\n'
        '   - Approval/dispatch strictly prevents negative stock\n'
        '   - Invoice for full order: Taxable Rs 6,000, IGST Rs 300, Total Rs 6,300'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--full-settlement',
            action='store_true',
            help='Also test subsequent final payment settlement of Rs 3,875'
        )

    def handle(self, *args, **options):
        full_settlement = options.get('full_settlement', False)
        self.stdout.write(self.style.NOTICE("=" * 70))
        self.stdout.write(self.style.NOTICE("  NIT TRICHY SALES MANAGEMENT BENCHMARK VERIFICATION"))
        self.stdout.write(self.style.NOTICE("=" * 70))

        # Clean prior test sales orders, invoices, dispatches, and payments if any to guarantee idempotency
        prior_orders = list(SalesOrder.objects.filter(order_number__in=['SO-BENCH-RET-A', 'SO-BENCH-DIST-B']))
        for order in prior_orders:
            for disp in Dispatch.objects.filter(sales_order=order):
                StockLedgerEntry.objects.filter(reference_type='SALES_DISPATCH', reference_id=disp.dispatch_number).delete()
                disp.delete()
            invoices = Invoice.objects.filter(sales_order=order)
            for inv in invoices:
                PaymentRecord.objects.filter(invoice=inv).delete()
                inv.delete()
            order.items.all().delete()
            order.delete()

        # 1. Execute baseline inventory and production benchmark to establish 238 finished packets
        call_command('seed_snacks_benchmark')
        call_command('run_nit_production_benchmark')

        User = get_user_model()
        admin_user = (
            User.objects.filter(role=CustomUser.Role.ADMIN, is_active=True).first()
            or User.objects.filter(is_superuser=True, is_active=True).first()
            or get_or_create_demo_user(CustomUser.Role.ADMIN)
        )
        salesman_user = (
            User.objects.filter(role=CustomUser.Role.SALESMAN, is_active=True).first()
            or get_or_create_demo_user(CustomUser.Role.SALESMAN)
        )

        sku = ProductPackSize.objects.get(sku_code='SKU-MRK-200G')
        uom_pcs = UnitOfMeasurement.objects.get(code='PCS')

        # Verify initial finished goods stock is exactly 238 packets
        initial_stock = sum(s.quantity_on_hand for s in StockItem.objects.filter(product_pack_size=sku, quantity_on_hand__gt=0))
        self.stdout.write(f"\n[1] Baseline Finished Stock on Hand: {initial_stock:.2f} packets (Opening 50 + Produced 188 = 238)")
        assert initial_stock == Decimal('238.00'), f"Expected 238 packets, got {initial_stock}"

        # ------------------------------------------------------------------
        # SCENARIO 1: Retailer A — Tamil Nadu
        # ------------------------------------------------------------------
        self.stdout.write(self.style.MIGRATE_HEADING("\n--- SCENARIO 1: Retailer A — Tamil Nadu (Intra-State GST) ---"))
        cust_a, _ = Customer.objects.get_or_create(
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

        order_a = SalesOrder.objects.create(
            order_number='SO-BENCH-RET-A',
            customer=cust_a,
            salesman=salesman_user,
            order_date=date.today(),
            delivery_state='Tamil Nadu',
            delivery_city='Chennai',
            status=SalesOrder.Status.SUBMITTED
        )
        SalesOrderItem.objects.create(
            sales_order=order_a,
            product_pack_size=sku,
            quantity=Decimal('150.00'),
            uom=uom_pcs,
            unit_price=Decimal('50.00')
        )
        order_a.update_totals()
        order_a.refresh_from_db()

        self.stdout.write(f"Order Created: {order_a.order_number} for 150 packets @ Rs 50.00")
        self.stdout.write(f" - Taxable Value: Rs {order_a.subtotal_amount}")
        self.stdout.write(f" - CGST (2.5%):  Rs {order_a.cgst_amount}")
        self.stdout.write(f" - SGST (2.5%):  Rs {order_a.sgst_amount}")
        self.stdout.write(f" - IGST (0.0%):  Rs {order_a.igst_amount}")
        self.stdout.write(f" - Grand Total:  Rs {order_a.total_amount}")

        assert order_a.subtotal_amount == Decimal('7500.00'), f"Expected 7500.00, got {order_a.subtotal_amount}"
        assert order_a.cgst_amount == Decimal('187.50'), f"Expected 187.50, got {order_a.cgst_amount}"
        assert order_a.sgst_amount == Decimal('187.50'), f"Expected 187.50, got {order_a.sgst_amount}"
        assert order_a.igst_amount == Decimal('0.00'), f"Expected 0.00, got {order_a.igst_amount}"
        assert order_a.total_amount == Decimal('7875.00'), f"Expected 7875.00, got {order_a.total_amount}"

        # Admin Approval
        approve_sales_order(order_a.pk, admin_user)
        order_a.refresh_from_db()
        self.stdout.write(f"Order Approved by Admin: {order_a.get_status_display()}")

        # Invoice Generation
        inv_a = generate_invoice_for_order(order_a.pk, admin_user)
        self.stdout.write(f"Tax Invoice Generated: {inv_a.invoice_number}")
        self.stdout.write(f" - Invoice Total: Rs {inv_a.grand_total}")
        self.stdout.write(f" - Seller GSTIN:  {inv_a.company_gstin} (Demo / Placeholder Verified)")
        assert inv_a.grand_total == Decimal('7875.00')

        # PDF Verification
        pdf_bytes = generate_invoice_pdf(inv_a)
        assert b"%PDF-1.4" in pdf_bytes
        assert b"7500.00" in pdf_bytes
        assert b"187.50" in pdf_bytes
        assert b"7875.00" in pdf_bytes
        assert b"150" in pdf_bytes
        self.stdout.write(f"PDF 1.4 Binary Generated ({len(pdf_bytes)} bytes) - All 150-packet figures verified in PDF stream.")

        # Dispatch 150 Packets
        disp_a = post_sales_dispatch(
            sales_order_id=order_a.pk,
            user=admin_user,
            carrier_name='Sri Murugan Roadways',
            vehicle_number='TN 45 AX 8810',
            lr_number='LR-BENCH-RET-A'
        )
        self.stdout.write(f"Dispatch Executed: {disp_a.dispatch_number} for 150 packets")

        # Verify Finished Goods Stock Decreased from 238 to 88
        stock_after_a = sum(s.quantity_on_hand for s in StockItem.objects.filter(product_pack_size=sku, quantity_on_hand__gt=0))
        self.stdout.write(f"Finished Goods Stock on Hand after Dispatch: {stock_after_a:.2f} packets (Expected: 88.00)")
        assert stock_after_a == Decimal('88.00'), f"Expected 88.00, got {stock_after_a}"

        # Verify Duplicate Dispatch and Invoice Prevention
        try:
            post_sales_dispatch(order_a.pk, admin_user)
            assert False, "Duplicate dispatch should have failed!"
        except ValidationError as e:
            self.stdout.write(f"Duplicate dispatch blocked successfully: {e}")

        try:
            generate_invoice_for_order(order_a.pk, admin_user)
            assert False, "Duplicate invoice should have failed!"
        except ValidationError as e:
            self.stdout.write(f"Duplicate invoice blocked successfully: {e}")

        # ------------------------------------------------------------------
        # SCENARIO 2: Distributor B — Karnataka
        # ------------------------------------------------------------------
        self.stdout.write(self.style.MIGRATE_HEADING("\n--- SCENARIO 2: Distributor B — Karnataka (Stock Shortage & Inter-State GST) ---"))
        cust_b, _ = Customer.objects.get_or_create(
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

        order_b = SalesOrder.objects.create(
            order_number='SO-BENCH-DIST-B',
            customer=cust_b,
            salesman=salesman_user,
            order_date=date.today(),
            delivery_state='Karnataka',
            delivery_city='Bengaluru',
            status=SalesOrder.Status.SUBMITTED
        )
        SalesOrderItem.objects.create(
            sales_order=order_b,
            product_pack_size=sku,
            quantity=Decimal('120.00'),
            uom=uom_pcs,
            unit_price=Decimal('50.00')
        )
        order_b.update_totals()
        order_b.refresh_from_db()

        self.stdout.write(f"Order Created: {order_b.order_number} for 120 packets @ Rs 50.00 (Destination: Karnataka)")
        
        # Verify Shortage is Exactly 32 Packets
        shortage_qty, is_short, avail, req = get_order_stock_shortage(order_b)
        order_shortage = order_b.get_stock_shortage()
        self.stdout.write(f"Stock Availability Analysis:")
        self.stdout.write(f" - Required Quantity:  {req:.2f} packets")
        self.stdout.write(f" - Available on Hand:  {avail:.2f} packets")
        self.stdout.write(f" - Shortage Quantity:  {shortage_qty:.2f} packets (Shortage verified: {order_shortage:.2f})")
        assert avail == Decimal('88.00'), f"Expected 88.00 available, got {avail}"
        assert req == Decimal('120.00'), f"Expected 120.00 required, got {req}"
        assert shortage_qty == Decimal('32.00'), f"Expected exactly 32.00 shortage, got {shortage_qty}"
        assert order_shortage == Decimal('32.00'), f"Expected exactly 32.00 shortage, got {order_shortage}"

        # Verify Approval Blocks Negative Stock
        try:
            approve_sales_order(order_b.pk, admin_user)
            assert False, "Approval should have been blocked due to shortage!"
        except ValidationError as e:
            self.stdout.write(f"Approval correctly rejected: {e}")

        # Verify Dispatch Blocks Negative Stock
        try:
            post_sales_dispatch(order_b.pk, admin_user)
            assert False, "Dispatch should have been blocked due to shortage!"
        except ValidationError as e:
            self.stdout.write(f"Dispatch correctly rejected: {e}")

        # Verify Full Invoice Calculation for 120-packet Order
        inv_b = generate_invoice_for_order(order_b.pk, admin_user, allow_unapproved=True)
        self.stdout.write(f"\nFull Order Invoice Calculation (Inter-State 5% IGST):")
        self.stdout.write(f" - Taxable Value: Rs {inv_b.taxable_amount} (Expected: Rs 6,000.00)")
        self.stdout.write(f" - CGST:          Rs {inv_b.cgst_amount} (Expected: Rs 0.00)")
        self.stdout.write(f" - SGST:          Rs {inv_b.sgst_amount} (Expected: Rs 0.00)")
        self.stdout.write(f" - IGST (5%):     Rs {inv_b.igst_amount} (Expected: Rs 300.00)")
        self.stdout.write(f" - Grand Total:   Rs {inv_b.grand_total} (Expected: Rs 6,300.00)")
        assert inv_b.taxable_amount == Decimal('6000.00'), f"Expected 6000.00, got {inv_b.taxable_amount}"
        assert inv_b.igst_amount == Decimal('300.00'), f"Expected 300.00, got {inv_b.igst_amount}"
        assert inv_b.grand_total == Decimal('6300.00'), f"Expected 6300.00, got {inv_b.grand_total}"

        # ------------------------------------------------------------------
        # SCENARIO 3: Payment Reconciliation on Retailer A Invoice
        # ------------------------------------------------------------------
        self.stdout.write(self.style.MIGRATE_HEADING("\n--- SCENARIO 3: Payment Reconciliation & Ledger Audit ---"))
        self.stdout.write(f"Invoice {inv_a.invoice_number} Initial Balance Due: Rs {inv_a.balance_due}")
        assert inv_a.balance_due == Decimal('7875.00')

        # Partial Payment (Benchmark Specification: Rs 4,000 received, Rs 3,875 outstanding)
        pay1 = record_invoice_payment(
            invoice_id=inv_a.pk,
            amount=Decimal('4000.00'),
            payment_mode=PaymentRecord.Mode.UPI,
            reference_no='UPI-ICICI-8812001',
            user=admin_user,
            notes='Initial advance settlement'
        )
        inv_a.refresh_from_db()
        self.stdout.write(f"Payment 1 Recorded: Rs 4,000.00 | Status: {inv_a.get_payment_status_display()} | Remaining: Rs {inv_a.balance_due}")
        assert inv_a.payment_status == Invoice.PaymentStatus.PARTIAL
        assert inv_a.amount_paid == Decimal('4000.00')
        assert inv_a.balance_due == Decimal('3875.00')

        if full_settlement:
            # Optional Final Payment Test
            pay2 = record_invoice_payment(
                invoice_id=inv_a.pk,
                amount=Decimal('3875.00'),
                payment_mode=PaymentRecord.Mode.NEFT_RTGS,
                reference_no='NEFT-SBI-449102',
                user=admin_user,
                notes='Full balance clearance'
            )
            inv_a.refresh_from_db()
            self.stdout.write(f"Payment 2 Recorded: Rs 3,875.00 | Status: {inv_a.get_payment_status_display()} | Remaining: Rs {inv_a.balance_due}")
            assert inv_a.payment_status == Invoice.PaymentStatus.PAID
            assert inv_a.amount_paid == Decimal('7875.00')
            assert inv_a.balance_due == Decimal('0.00')

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 70))
        self.stdout.write(self.style.SUCCESS("  ALL NIT TRICHY BENCHMARK INVARIANTS 100% VERIFIED"))
        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(
            f"1. Opening Stock: Flour 100kg, Oil 30L, Spice 5kg, Pouches 500, Cartons 30, FG 50 pkts\n"
            f"2. Purchase: Flour 60kg @ Rs 45/kg (Pre-prod stock: 160kg)\n"
            f"3. Production: Flour 40kg, Oil 10.5L (+5%), Spice 1.2kg, Good 188 pkts (-6% yield), Pouches 194 (6 dmg), Cartons 9\n"
            f"4. Production Cost: Rs 5,855.00 | Unit Cost: Rs 31.14 / pkt\n"
            f"5. Retailer A: 150 pkts, Taxable Rs 7,500, CGST Rs 187.50, SGST Rs 187.50, Total Rs 7,875\n"
            f"   - Dispatched: 150 pkts | Closing FG: 88 pkts | Payment: Rs {inv_a.amount_paid} | Outstanding: Rs {inv_a.balance_due}\n"
            f"6. Distributor B: 120 pkts requested, 88 avail, Shortage 32 pkts | Blocked negative stock\n"
            f"   - Full Invoice: Taxable Rs 6,000, 5% IGST Rs 300, Total Rs 6,300\n"
            f"{'=' * 70}\n"
        )
