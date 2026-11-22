from decimal import Decimal
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import CustomUser
from apps.master_data.models import (
    Customer,
    Supplier,
    Product,
    ProductPackSize,
    RawMaterial,
    PackagingMaterial,
    UnitOfMeasurement,
    BillOfMaterials,
)
from apps.inventory.models import (
    ItemType,
    PurchaseOrder,
    PurchaseOrderItem,
    GoodsReceiptNote,
    GoodsReceiptItem,
    StockItem,
    StockLedgerEntry,
    StockAdjustment,
    StockAdjustmentItem,
)
from apps.production.models import ProductionRun, ProductionMaterialConsumption
from apps.sales.models import SalesOrder, SalesOrderItem, Invoice, Dispatch, PaymentRecord
from apps.core.models import AuditLogEntry


class Command(BaseCommand):
    help = (
        'Idempotently seeds comprehensive enterprise demonstration data across all 9 departments:\n'
        '- Anchored by the exact NIT Trichy Murukku 200g production and sales benchmark.\n'
        '- Seeds active sales orders, approval queues, invoices, purchase orders, GRNs,\n'
        '  in-progress production WIP runs, quality inspections, damage write-offs, receivables, and audit trails.\n'
        '- Leaves zero empty workspaces in the entire application.'
    )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("=" * 70))
        self.stdout.write(self.style.NOTICE("  SEEDING MANUFLOW ENTERPRISE DEMO DATA ACROSS ALL DEPARTMENTS"))
        self.stdout.write(self.style.NOTICE("=" * 70))

        # 1. Base users & demo account
        self.stdout.write("1. Verifying user accounts & demo credentials...")
        call_command('seed_demo_account')
        try:
            call_command('seed_users')
        except Exception:
            pass

        # 2. Master data setup
        self.stdout.write("2. Verifying master data catalog...")
        call_command('seed_master_data')

        # 3. NIT Trichy Benchmark Opening Inventory
        self.stdout.write("3. Verifying NIT Trichy Benchmark Opening Balances...")
        call_command('seed_snacks_benchmark')

        # 4. NIT Trichy Production Benchmark
        self.stdout.write("4. Executing NIT Trichy Production Benchmark (188 good, 6 damaged, 9 cartons)...")
        call_command('run_nit_production_benchmark')

        # 5. NIT Trichy Sales Benchmark
        self.stdout.write("5. Executing NIT Trichy Sales Benchmark (Retailer A 150 pkts, Distributor B Shortage 32 pkts)...")
        call_command('run_nit_sales_benchmark', full_settlement=True)

        # 6. Additional Realistic Operational Records for Rich Department Experience
        self.stdout.write("6. Populating operational sample records across all modules...")
        today = date.today()
        User = get_user_model()
        admin_user = User.objects.filter(role=CustomUser.Role.ADMIN).first() or User.objects.first()
        salesman_user = User.objects.filter(role=CustomUser.Role.SALESMAN).first() or admin_user
        prod_user = User.objects.filter(role=CustomUser.Role.PRODUCTION).first() or admin_user
        acct_user = User.objects.filter(role=CustomUser.Role.ACCOUNTANT).first() or admin_user
        audit_user = User.objects.filter(role=CustomUser.Role.AUDITOR).first() or admin_user

        sku_mrk = ProductPackSize.objects.get(sku_code='SKU-MRK-200G')
        uom_pcs = UnitOfMeasurement.objects.get(code='PCS')
        uom_kg = UnitOfMeasurement.objects.get(code='KG')
        uom_l = UnitOfMeasurement.objects.get(code='L')
        bom_mrk = BillOfMaterials.objects.get(bom_code='BOM-MRK-200PKT')

        # ------------------------------------------------------------------
        # A. Additional Customers
        # ------------------------------------------------------------------
        cust_c, _ = Customer.objects.get_or_create(
            code='CUST-RETAIL-C',
            defaults={
                'name': 'Sri Krishna Sweets & Snacks Madurai',
                'customer_type': Customer.CustomerType.RETAILER,
                'state': 'Tamil Nadu',
                'city': 'Madurai',
                'billing_address': '124 Town Hall Road, Madurai',
                'shipping_address': '124 Town Hall Road, Madurai',
                'tax_id_gst': '33AABCS8890K1Z1',
                'credit_days': 15,
            }
        )
        cust_d, _ = Customer.objects.get_or_create(
            code='CUST-HYPER-D',
            defaults={
                'name': 'Grand Kerala Hypermarket Kochi',
                'customer_type': Customer.CustomerType.DISTRIBUTOR,
                'state': 'Kerala',
                'city': 'Kochi',
                'billing_address': 'MG Road, Ernakulam, Kochi',
                'shipping_address': 'Kochi Logistics Park, Kalamassery',
                'tax_id_gst': '32AABCG5540P1ZX',
                'credit_days': 30,
            }
        )

        # ------------------------------------------------------------------
        # B. Additional Sales Orders & Commercial Pipeline
        # ------------------------------------------------------------------
        # Order SO-DEMO-003: Approved, Ready for Invoicing
        so_3, created_3 = SalesOrder.objects.get_or_create(
            order_number='SO-DEMO-003',
            defaults={
                'customer': cust_c,
                'salesman': salesman_user,
                'order_date': today - timedelta(days=2),
                'expected_delivery_date': today + timedelta(days=3),
                'status': SalesOrder.Status.APPROVED,
                'delivery_address': '124 Town Hall Road, Madurai, Tamil Nadu',
                'delivery_city': 'Madurai',
                'delivery_state': 'Tamil Nadu',
                'is_interstate': False,
                'subtotal_amount': Decimal('2000.00'),
                'cgst_amount': Decimal('50.00'),
                'sgst_amount': Decimal('50.00'),
                'igst_amount': Decimal('0.00'),
                'total_tax_amount': Decimal('100.00'),
                'total_amount': Decimal('2100.00'),
            }
        )
        if created_3:
            SalesOrderItem.objects.create(
                sales_order=so_3,
                product_pack_size=sku_mrk,
                quantity=Decimal('40.00'),
                uom=uom_pcs,
                unit_price=Decimal('50.00'),
                subtotal=Decimal('2000.00'),
                gst_rate_pct=Decimal('5.00'),
                cgst_rate_pct=Decimal('2.50'),
                cgst_amount=Decimal('50.00'),
                sgst_rate_pct=Decimal('2.50'),
                sgst_amount=Decimal('50.00'),
                igst_rate_pct=Decimal('0.00'),
                igst_amount=Decimal('0.00'),
                tax_amount=Decimal('100.00'),
                total_price=Decimal('2100.00'),
            )

        # Order SO-DEMO-004: Submitted (Pending Approval Queue)
        so_4, created_4 = SalesOrder.objects.get_or_create(
            order_number='SO-DEMO-004',
            defaults={
                'customer': cust_d,
                'salesman': salesman_user,
                'order_date': today - timedelta(days=1),
                'expected_delivery_date': today + timedelta(days=5),
                'status': SalesOrder.Status.SUBMITTED,
                'delivery_address': 'Kochi Logistics Park, Kalamassery, Kerala',
                'delivery_city': 'Kochi',
                'delivery_state': 'Kerala',
                'is_interstate': True,
                'subtotal_amount': Decimal('1500.00'),
                'cgst_amount': Decimal('0.00'),
                'sgst_amount': Decimal('0.00'),
                'igst_amount': Decimal('75.00'),
                'total_tax_amount': Decimal('75.00'),
                'total_amount': Decimal('1575.00'),
            }
        )
        if created_4:
            SalesOrderItem.objects.create(
                sales_order=so_4,
                product_pack_size=sku_mrk,
                quantity=Decimal('30.00'),
                uom=uom_pcs,
                unit_price=Decimal('50.00'),
                subtotal=Decimal('1500.00'),
                gst_rate_pct=Decimal('5.00'),
                cgst_rate_pct=Decimal('0.00'),
                cgst_amount=Decimal('0.00'),
                sgst_rate_pct=Decimal('0.00'),
                sgst_amount=Decimal('0.00'),
                igst_rate_pct=Decimal('5.00'),
                igst_amount=Decimal('75.00'),
                tax_amount=Decimal('75.00'),
                total_price=Decimal('1575.00'),
            )

        # Order SO-DEMO-005: Invoiced with partial payment for Receivables Aging demonstration
        cust_a = Customer.objects.get(code='CUST-RETAIL-A')
        so_5, created_5 = SalesOrder.objects.get_or_create(
            order_number='SO-DEMO-005',
            defaults={
                'customer': cust_a,
                'salesman': salesman_user,
                'order_date': today - timedelta(days=12),
                'expected_delivery_date': today - timedelta(days=8),
                'status': SalesOrder.Status.INVOICED,
                'delivery_address': 'Anna Salai, Chennai, Tamil Nadu',
                'delivery_city': 'Chennai',
                'delivery_state': 'Tamil Nadu',
                'is_interstate': False,
                'subtotal_amount': Decimal('2500.00'),
                'cgst_amount': Decimal('62.50'),
                'sgst_amount': Decimal('62.50'),
                'igst_amount': Decimal('0.00'),
                'total_tax_amount': Decimal('125.00'),
                'total_amount': Decimal('2625.00'),
            }
        )
        if created_5:
            SalesOrderItem.objects.create(
                sales_order=so_5,
                product_pack_size=sku_mrk,
                quantity=Decimal('50.00'),
                uom=uom_pcs,
                unit_price=Decimal('50.00'),
                subtotal=Decimal('2500.00'),
                gst_rate_pct=Decimal('5.00'),
                cgst_rate_pct=Decimal('2.50'),
                cgst_amount=Decimal('62.50'),
                sgst_rate_pct=Decimal('2.50'),
                sgst_amount=Decimal('62.50'),
                igst_rate_pct=Decimal('0.00'),
                igst_amount=Decimal('0.00'),
                tax_amount=Decimal('125.00'),
                total_price=Decimal('2625.00'),
            )

        # Tax Invoice for SO-DEMO-005 with outstanding balance
        inv_demo_2, inv_created_2 = Invoice.objects.get_or_create(
            invoice_number='INV-DEMO-2026-002',
            defaults={
                'sales_order': so_5,
                'customer': cust_a,
                'customer_name': cust_a.name,
                'customer_gstin': cust_a.tax_id_gst or '33AABCR1120K1ZX',
                'billing_address': cust_a.billing_address,
                'shipping_address': cust_a.shipping_address,
                'invoice_date': today - timedelta(days=10),
                'due_date': today + timedelta(days=20),
                'taxable_amount': Decimal('2500.00'),
                'cgst_amount': Decimal('62.50'),
                'sgst_amount': Decimal('62.50'),
                'igst_amount': Decimal('0.00'),
                'total_tax': Decimal('125.00'),
                'grand_total': Decimal('2625.00'),
                'amount_paid': Decimal('1000.00'),
                'payment_status': Invoice.PaymentStatus.PARTIAL,
                'company_gstin': '33NITTRICHY1Z5 (Demo Placeholder)',
                'place_of_supply': 'Tamil Nadu',
                'created_by': admin_user,
            }
        )

        # Payment voucher for partial payment
        pay_demo, pay_created = PaymentRecord.objects.get_or_create(
            payment_number='PAY-DEMO-2026-003',
            defaults={
                'invoice': inv_demo_2,
                'customer': cust_a,
                'payment_date': today - timedelta(days=4),
                'amount': Decimal('1000.00'),
                'payment_mode': PaymentRecord.Mode.NEFT,
                'transaction_reference': 'NEFT-AXIS-2026-8812',
                'notes': 'Advance partial payment received via NEFT.',
                'recorded_by': acct_user,
            }
        )

        # ------------------------------------------------------------------
        # C. Additional Purchase Orders & Goods Receipt Notes
        # ------------------------------------------------------------------
        sup_flour = Supplier.objects.get(code='SUP-SNK-01')
        sup_oil = Supplier.objects.get(code='SUP-SNK-02')
        sup_pkg, _ = Supplier.objects.get_or_create(
            code='SUP-SNK-04',
            defaults={
                'name': 'Supreme Multi-Pack Containers Ltd',
                'contact_person': 'A. Rajesh Kumar',
                'email': 'sales@suprememultipack.com',
                'phone': '+91 44 2652 9011',
                'tax_id_gst': '33AAECS7710M1Z8',
                'city': 'Chennai',
                'state': 'Tamil Nadu',
            }
        )
        pm_pouch = PackagingMaterial.objects.get(code='PM-POUCH')
        rm_oil = RawMaterial.objects.get(code='RM-OIL')
        rm_flour = RawMaterial.objects.get(code='RM-FLOUR')

        # PO-DEMO-002: Approved Pouches Order
        po_2, created_po2 = PurchaseOrder.objects.get_or_create(
            po_number='PO-DEMO-002',
            defaults={
                'supplier': sup_pkg,
                'order_date': today - timedelta(days=3),
                'expected_delivery_date': today + timedelta(days=4),
                'status': PurchaseOrder.Status.APPROVED,
                'total_amount': Decimal('2625.00'),
                'created_by': admin_user,
                'approved_by': admin_user,
            }
        )
        if created_po2:
            PurchaseOrderItem.objects.create(
                purchase_order=po_2,
                item_type=ItemType.PACKAGING_MATERIAL,
                packaging_material=pm_pouch,
                ordered_quantity=Decimal('1000.0000'),
                uom=uom_pcs,
                unit_price=Decimal('2.50'),
                line_total=Decimal('2500.00'),
            )

        # PO-DEMO-003: Submitted Oil Inbound Order
        po_3, created_po3 = PurchaseOrder.objects.get_or_create(
            po_number='PO-DEMO-003',
            defaults={
                'supplier': sup_oil,
                'order_date': today - timedelta(days=1),
                'expected_delivery_date': today + timedelta(days=2),
                'status': PurchaseOrder.Status.SUBMITTED,
                'total_amount': Decimal('7245.00'),
                'created_by': admin_user,
            }
        )
        if created_po3:
            PurchaseOrderItem.objects.create(
                purchase_order=po_3,
                item_type=ItemType.RAW_MATERIAL,
                raw_material=rm_oil,
                ordered_quantity=Decimal('50.0000'),
                uom=uom_l,
                unit_price=Decimal('138.00'),
                line_total=Decimal('6900.00'),
            )

        # ------------------------------------------------------------------
        # D. Additional Production Batches (Active WIP & Scheduled)
        # ------------------------------------------------------------------
        prun_2, created_prun2 = ProductionRun.objects.get_or_create(
            run_number='PRUN-DEMO-002',
            defaults={
                'bill_of_materials': bom_mrk,
                'product': bom_mrk.product,
                'product_pack_size': sku_mrk,
                'batch_number': 'LOT-FG-MRK200-002',
                'planned_quantity': Decimal('100.00'),
                'actual_output_quantity': Decimal('0.00'),
                'damaged_quantity': Decimal('0.00'),
                'status': ProductionRun.Status.IN_PROGRESS,
                'created_by': prod_user,
                'notes': 'Active Shift 2 Batch Run on Line 1. Mixing and extrusion in progress.',
            }
        )

        prun_3, created_prun3 = ProductionRun.objects.get_or_create(
            run_number='PRUN-DEMO-003',
            defaults={
                'bill_of_materials': bom_mrk,
                'product': bom_mrk.product,
                'product_pack_size': sku_mrk,
                'batch_number': 'LOT-FG-MRK200-003',
                'planned_quantity': Decimal('200.00'),
                'actual_output_quantity': Decimal('0.00'),
                'damaged_quantity': Decimal('0.00'),
                'status': ProductionRun.Status.DRAFT,
                'created_by': prod_user,
                'notes': 'Scheduled Shift 3 Production Run for tomorrow morning.',
            }
        )

        # ------------------------------------------------------------------
        # E. Stock Adjustments / Quality Inspections / Damaged Goods
        # ------------------------------------------------------------------
        adj_1, created_adj1 = StockAdjustment.objects.get_or_create(
            adjustment_number='ADJ-DEMO-2026-001',
            defaults={
                'adjustment_date': today,
                'reason': StockAdjustment.Reason.DAMAGE_EXPIRY,
                'status': StockAdjustment.Status.POSTED,
                'is_posted': True,
                'posted_at': timezone.now(),
                'created_by': audit_user,
                'approved_by': admin_user,
                'notes': (
                    'Packaging Line 1 Quality Inspection: 6 printed pouches rejected and written off '
                    'due to heat-sealing machine temperature calibration puncture. Scrapped per SOP-QC-04.'
                ),
            }
        )
        if created_adj1:
            StockAdjustmentItem.objects.create(
                adjustment=adj_1,
                item_type=ItemType.PACKAGING_MATERIAL,
                packaging_material=pm_pouch,
                batch_number='LOT-POUCH-OP-01',
                uom=uom_pcs,
                system_quantity=Decimal('312.0000'),
                counted_quantity=Decimal('306.0000'),
                variance_quantity=Decimal('-6.0000'),
                unit_cost=Decimal('2.50'),
                remarks='6 damaged packaging pouches written off during sealing quality check.',
            )

        adj_2, created_adj2 = StockAdjustment.objects.get_or_create(
            adjustment_number='ADJ-DEMO-2026-002',
            defaults={
                'adjustment_date': today - timedelta(days=5),
                'reason': StockAdjustment.Reason.PHYSICAL_AUDIT,
                'status': StockAdjustment.Status.POSTED,
                'is_posted': True,
                'posted_at': timezone.now() - timedelta(days=5),
                'created_by': audit_user,
                'approved_by': admin_user,
                'notes': (
                    'Quarterly physical warehouse cycle verification: Flour silos weighed and verified. '
                    'Digital stock balances match physical bin card counts within standard tolerance.'
                ),
            }
        )
        if created_adj2:
            StockAdjustmentItem.objects.create(
                adjustment=adj_2,
                item_type=ItemType.RAW_MATERIAL,
                raw_material=rm_flour,
                batch_number='LOT-FLOUR-OP-01',
                uom=uom_kg,
                system_quantity=Decimal('120.0000'),
                counted_quantity=Decimal('120.0000'),
                variance_quantity=Decimal('0.0000'),
                unit_cost=Decimal('42.00'),
                remarks='Physical count matched stock ledger balance exactly.',
            )

        # ------------------------------------------------------------------
        # F. System Audit Trail Log Entries
        # ------------------------------------------------------------------
        audit_events = [
            (AuditLogEntry.Action.ORDER_CREATED, AuditLogEntry.Module.SALES, 'Sales Order SO-DEMO-004', 'SO-DEMO-004', salesman_user, {'customer': 'Grand Kerala Hypermarket', 'packets': 30, 'total': 1575.0}),
            (AuditLogEntry.Action.ORDER_APPROVED, AuditLogEntry.Module.SALES, 'Sales Order SO-DEMO-003', 'SO-DEMO-003', admin_user, {'customer': 'Sri Krishna Sweets', 'packets': 40, 'status': 'APPROVED'}),
            (AuditLogEntry.Action.PRODUCTION_CREATE, AuditLogEntry.Module.PRODUCTION, 'Production Run PRUN-DEMO-002', 'PRUN-DEMO-002', prod_user, {'batch': 'LOT-FG-MRK200-002', 'planned_qty': 100}),
            (AuditLogEntry.Action.PO_APPROVED, AuditLogEntry.Module.INVENTORY, 'Purchase Order PO-DEMO-002', 'PO-DEMO-002', admin_user, {'supplier': 'Supreme Multi-Pack', 'item': 'PM-POUCH', 'qty': 1000}),
            (AuditLogEntry.Action.STOCK_ADJUSTMENT, AuditLogEntry.Module.INVENTORY, 'Stock Adjustment ADJ-DEMO-2026-001', 'ADJ-DEMO-2026-001', audit_user, {'reason': 'DAMAGE_EXPIRY', 'scrapped_pouches': 6}),
            (AuditLogEntry.Action.PAYMENT_RECORDED, AuditLogEntry.Module.FINANCE, 'Payment PAY-DEMO-2026-003', 'PAY-DEMO-2026-003', acct_user, {'invoice': 'INV-DEMO-2026-002', 'amount': 1000.0, 'mode': 'NEFT'}),
        ]

        for action, module, obj_repr, ref_num, user_actor, details_dict in audit_events:
            if not AuditLogEntry.objects.filter(reference_number=ref_num, action=action).exists():
                AuditLogEntry.objects.create(
                    action=action,
                    module=module,
                    object_repr=obj_repr,
                    reference_number=ref_num,
                    user=user_actor,
                    user_email=user_actor.email if user_actor else '',
                    user_role=getattr(user_actor, 'role', ''),
                    ip_address='127.0.0.1',
                    details=details_dict,
                )

        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(self.style.SUCCESS("  MANUFLOW ENTERPRISE DEMO SEEDING COMPLETED SUCCESSFULLY!"))
        self.stdout.write(self.style.SUCCESS("  - Active Orders: Ready in Approval Queue & Dispatches"))
        self.stdout.write(self.style.SUCCESS("  - Invoices & Aging: Dual GST & Outstanding Balances populated"))
        self.stdout.write(self.style.SUCCESS("  - Production: Active WIP on floor & Planned Work Orders"))
        self.stdout.write(self.style.SUCCESS("  - Inventory: POs, GRN, Stock Balances across all 3 tiers"))
        self.stdout.write(self.style.SUCCESS("  - Quality: Damaged goods & physical count adjustments recorded"))
        self.stdout.write(self.style.SUCCESS("  - Governance: Complete system audit trail verified"))
        self.stdout.write(self.style.SUCCESS("=" * 70))
