from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.core.management import call_command
from django.core.exceptions import ValidationError

from apps.accounts.models import CustomUser
from apps.master_data.models import (
    Supplier,
    RawMaterial,
    PackagingMaterial,
    Product,
    ProductPackSize,
    UnitOfMeasurement,
    UnitConversion,
    BillOfMaterials,
    BOMItem,
)
from apps.inventory.models import (
    ItemType,
    MovementType,
    PurchaseOrder,
    PurchaseOrderItem,
    GoodsReceiptNote,
    GoodsReceiptItem,
    StockItem,
    StockLedgerEntry,
    StockAdjustment,
    StockAdjustmentItem,
)
from apps.inventory.services import (
    record_stock_movement,
    post_goods_receipt,
    post_stock_adjustment,
)


class InventoryLedgerAndServiceTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email='admin@nit.edu', username='admin_inv', password='Pass12345!',
            role=CustomUser.Role.ADMIN, is_staff=True
        )
        self.kg = UnitOfMeasurement.objects.create(code='KG', name='Kilogram', uom_type='WEIGHT')
        self.supplier = Supplier.objects.create(code='SUP-TEST-01', name='Madurai Flour Mills')
        self.raw_mat = RawMaterial.objects.create(
            code='RM-RICE-01', name='Steamed Rice Flour', uom=self.kg,
            standard_cost=Decimal('50.00'), reorder_level=Decimal('100.00'),
            preferred_supplier=self.supplier
        )

    def test_record_stock_movement_math_integrity(self):
        # 1. Opening balance: 0 + 200 = 200
        entry1 = record_stock_movement(
            item_type=ItemType.RAW_MATERIAL,
            movement_type=MovementType.OPENING_BALANCE,
            quantity_change=Decimal('200.0000'),
            uom=self.kg,
            unit_cost=Decimal('50.00'),
            reference_type='OPENING',
            reference_id='INIT-01',
            performed_by=self.user,
            raw_material=self.raw_mat,
            batch_number='LOT-TEST-01'
        )
        self.assertEqual(entry1.opening_quantity, Decimal('0.0000'))
        self.assertEqual(entry1.quantity_change, Decimal('200.0000'))
        self.assertEqual(entry1.closing_quantity, Decimal('200.0000'))
        self.assertEqual(entry1.opening_quantity + entry1.quantity_change, entry1.closing_quantity)

        # 2. Additional receipt: 200 + 100 = 300
        entry2 = record_stock_movement(
            item_type=ItemType.RAW_MATERIAL,
            movement_type=MovementType.PURCHASE_RECEIPT,
            quantity_change=Decimal('100.0000'),
            uom=self.kg,
            unit_cost=Decimal('50.00'),
            reference_type='GRN',
            reference_id='GRN-01',
            performed_by=self.user,
            raw_material=self.raw_mat,
            batch_number='LOT-TEST-01'
        )
        self.assertEqual(entry2.opening_quantity, Decimal('200.0000'))
        self.assertEqual(entry2.closing_quantity, Decimal('300.0000'))

        # Check real-time StockItem
        stock = StockItem.objects.get(raw_material=self.raw_mat, batch_number='LOT-TEST-01')
        self.assertEqual(stock.quantity_on_hand, Decimal('300.0000'))

    def test_prevent_negative_stock(self):
        # Initial stock 50 KG
        record_stock_movement(
            item_type=ItemType.RAW_MATERIAL,
            movement_type=MovementType.OPENING_BALANCE,
            quantity_change=Decimal('50.0000'),
            uom=self.kg,
            unit_cost=Decimal('50.00'),
            reference_type='INIT',
            reference_id='INIT-02',
            performed_by=self.user,
            raw_material=self.raw_mat,
            batch_number='LOT-NEG-01'
        )

        # Attempt to issue 60 KG -> must raise ValidationError
        with self.assertRaises(ValidationError):
            record_stock_movement(
                item_type=ItemType.RAW_MATERIAL,
                movement_type=MovementType.STOCK_ADJUSTMENT_OUT,
                quantity_change=Decimal('-60.0000'),
                uom=self.kg,
                unit_cost=Decimal('50.00'),
                reference_type='ADJUSTMENT',
                reference_id='ADJ-TEST',
                performed_by=self.user,
                raw_material=self.raw_mat,
                batch_number='LOT-NEG-01'
            )

    def test_post_goods_receipt_and_prevent_duplicate(self):
        # Create PO
        po = PurchaseOrder.objects.create(
            po_number='PO-TEST-01',
            supplier=self.supplier,
            order_date=date.today(),
            status=PurchaseOrder.Status.APPROVED,
            created_by=self.user
        )
        po_item = PurchaseOrderItem.objects.create(
            purchase_order=po,
            item_type=ItemType.RAW_MATERIAL,
            raw_material=self.raw_mat,
            ordered_quantity=Decimal('500.0000'),
            uom=self.kg,
            unit_price=Decimal('50.00')
        )
        po.update_totals()

        # Create GRN
        grn = GoodsReceiptNote.objects.create(
            grn_number='GRN-TEST-01',
            purchase_order=po,
            supplier=self.supplier,
            received_date=date.today(),
            received_by=self.user
        )
        GoodsReceiptItem.objects.create(
            grn=grn,
            po_item=po_item,
            item_type=ItemType.RAW_MATERIAL,
            raw_material=self.raw_mat,
            received_quantity=Decimal('500.0000'),
            rejected_quantity=Decimal('0.0000'),
            accepted_quantity=Decimal('500.0000'),
            uom=self.kg,
            unit_price=Decimal('50.00'),
            batch_number='LOT-GRN-01'
        )

        # Post GRN
        post_goods_receipt(grn.pk, self.user)
        grn.refresh_from_db()
        po.refresh_from_db()
        po_item.refresh_from_db()

        self.assertTrue(grn.is_posted)
        self.assertEqual(grn.status, GoodsReceiptNote.Status.POSTED)
        self.assertEqual(po_item.received_quantity, Decimal('500.0000'))
        self.assertEqual(po.status, PurchaseOrder.Status.RECEIVED)

        # Check stock balance
        stock = StockItem.objects.get(raw_material=self.raw_mat, batch_number='LOT-GRN-01')
        self.assertEqual(stock.quantity_on_hand, Decimal('500.0000'))

        # Attempt to post duplicate GRN -> must raise ValidationError
        with self.assertRaises(ValidationError):
            post_goods_receipt(grn.pk, self.user)

    def test_post_stock_adjustment(self):
        # Establish stock of 100 KG
        record_stock_movement(
            item_type=ItemType.RAW_MATERIAL,
            movement_type=MovementType.OPENING_BALANCE,
            quantity_change=Decimal('100.0000'),
            uom=self.kg,
            unit_cost=Decimal('50.00'),
            reference_type='INIT',
            reference_id='INIT-ADJ',
            performed_by=self.user,
            raw_material=self.raw_mat,
            batch_number='LOT-ADJ-01'
        )

        # Audit found 95 KG (Variance -5 KG)
        adj = StockAdjustment.objects.create(
            adjustment_number='ADJ-TEST-01',
            adjustment_date=date.today(),
            reason=StockAdjustment.Reason.PHYSICAL_AUDIT,
            created_by=self.user
        )
        StockAdjustmentItem.objects.create(
            adjustment=adj,
            item_type=ItemType.RAW_MATERIAL,
            raw_material=self.raw_mat,
            batch_number='LOT-ADJ-01',
            uom=self.kg,
            system_quantity=Decimal('100.0000'),
            counted_quantity=Decimal('95.0000'),
            variance_quantity=Decimal('-5.0000'),
            unit_cost=Decimal('50.00')
        )

        # Post adjustment
        post_stock_adjustment(adj.pk, self.user)
        adj.refresh_from_db()
        self.assertTrue(adj.is_posted)

        # Stock balance must be exactly 95.0000
        stock = StockItem.objects.get(raw_material=self.raw_mat, batch_number='LOT-ADJ-01')
        self.assertEqual(stock.quantity_on_hand, Decimal('95.0000'))

        # Duplicate post must fail
        with self.assertRaises(ValidationError):
            post_stock_adjustment(adj.pk, self.user)


class InventoryRoleAndViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = 'UniversalPass123'

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

        self.kg = UnitOfMeasurement.objects.create(code='KG', name='Kilogram', uom_type='WEIGHT')
        self.supplier = Supplier.objects.create(code='SUP-VIEW-01', name='Trichy Agro')
        self.raw_mat = RawMaterial.objects.create(
            code='RM-BESAN-01', name='Besan Flour', uom=self.kg,
            standard_cost=Decimal('80.00'), reorder_level=Decimal('200.00'),
            preferred_supplier=self.supplier
        )

        self.po = PurchaseOrder.objects.create(
            po_number='PO-VIEW-001',
            supplier=self.supplier,
            order_date=date.today(),
            status=PurchaseOrder.Status.APPROVED,
            created_by=self.admin
        )

    def test_inventory_dashboard_access(self):
        # Unauthenticated -> redirect to login
        res = self.client.get(reverse('inventory_dashboard'))
        self.assertEqual(res.status_code, 302)

        # Authenticated user -> 200 OK
        self.client.login(username='admin_u', password=self.password)
        res = self.client.get(reverse('inventory_dashboard'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Inventory & Procurement Observatory")

    def test_salesman_cannot_create_purchase_order(self):
        self.client.login(username='sales_u', password=self.password)
        res = self.client.get(reverse('purchase_order_create'))
        self.assertEqual(res.status_code, 403)

    def test_auditor_read_only_access(self):
        self.client.login(username='audit_u', password=self.password)

        # Auditor can view PO detail
        res = self.client.get(reverse('purchase_order_detail', kwargs={'pk': self.po.pk}))
        self.assertEqual(res.status_code, 200)

        # Auditor cannot approve PO -> 403
        res = self.client.post(reverse('purchase_order_approve', kwargs={'pk': self.po.pk}))
        self.assertEqual(res.status_code, 403)

        # Auditor can view stock ledger audit trail
        res = self.client.get(reverse('stock_ledger_list'))
        self.assertEqual(res.status_code, 200)

    def test_production_can_create_po(self):
        self.client.login(username='prod_u', password=self.password)
        res = self.client.get(reverse('purchase_order_create'))
        self.assertEqual(res.status_code, 200)

    def test_stock_summary_low_stock_filter(self):
        # Stock = 50 KG, reorder_level = 200 KG -> Low Stock!
        record_stock_movement(
            item_type=ItemType.RAW_MATERIAL,
            movement_type=MovementType.OPENING_BALANCE,
            quantity_change=Decimal('50.0000'),
            uom=self.kg,
            unit_cost=Decimal('80.00'),
            reference_type='INIT',
            reference_id='INIT-LS',
            performed_by=self.admin,
            raw_material=self.raw_mat,
            batch_number='LOT-LS-01'
        )

        self.client.login(username='admin_u', password=self.password)
        res = self.client.get(reverse('stock_summary') + '?low_stock=1')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Besan Flour")
        self.assertContains(res, "Reorder Alert")


class ExactBenchmarkDataTests(TestCase):
    """
    Automated test suite verifying the EXACT NIT Trichy Problem Statement Benchmark Data:
    - Flour: 100 kg opening at Rs 42/kg; Purchase: 60 kg at Rs 45/kg (Closing: 160 kg)
    - Oil: 30 L opening at Rs 140/L
    - Spice mix: 5 kg opening at Rs 200/kg
    - Pouches: 500 pcs opening at Rs 2.50 each
    - Cartons: 30 pcs opening at Rs 15 each (20 packets/carton)
    - Finished Murukku 200g: 50 packets opening, Selling price Rs 50 before 5% GST (MRP Rs 52.50)
    - BOM: Flour 40 kg, Oil 10 L, Spice 1.2 kg, Pouches 200, Cartons 10 -> Expected output: 200 packets
    - Inventory ledger mathematical integrity: Opening + Receipts - Issues = Closing
    - Command idempotency: No duplicate records when re-seeded.
    """

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            email='admin@nit.edu', username='admin_benchmark', password='Pass12345!',
            role=CustomUser.Role.ADMIN, is_staff=True, is_superuser=True
        )

    def test_exact_benchmark_master_data_and_rates(self):
        call_command('seed_snacks_benchmark')

        # 1. Flour
        flour = RawMaterial.objects.get(code='RM-FLOUR')
        self.assertEqual(flour.name, 'Flour')
        self.assertEqual(flour.uom.code, 'KG')
        self.assertEqual(flour.standard_cost, Decimal('42.00'))

        # 2. Oil
        oil = RawMaterial.objects.get(code='RM-OIL')
        self.assertEqual(oil.name, 'Oil')
        self.assertEqual(oil.uom.code, 'L')
        self.assertEqual(oil.standard_cost, Decimal('140.00'))

        # 3. Spice mix
        spice = RawMaterial.objects.get(code='RM-SPICE')
        self.assertEqual(spice.name, 'Spice mix')
        self.assertEqual(spice.uom.code, 'KG')
        self.assertEqual(spice.standard_cost, Decimal('200.00'))

        # 4. Pouches
        pouches = PackagingMaterial.objects.get(code='PM-POUCH')
        self.assertEqual(pouches.name, 'Pouches')
        self.assertEqual(pouches.uom.code, 'PCS')
        self.assertEqual(pouches.standard_cost, Decimal('2.50'))

        # 5. Cartons (20 packets/carton)
        cartons = PackagingMaterial.objects.get(code='PM-CARTON')
        self.assertEqual(cartons.uom.code, 'PCS')
        self.assertEqual(cartons.standard_cost, Decimal('15.00'))

        # 6. Unit conversion: 1 BOX = 20 PCS (20 packets/carton)
        uom_box = UnitOfMeasurement.objects.get(code='BOX')
        uom_pcs = UnitOfMeasurement.objects.get(code='PCS')
        conv = UnitConversion.objects.get(from_uom=uom_box, to_uom=uom_pcs)
        self.assertEqual(conv.multiplier, Decimal('20.000000'))

        # 7. Finished Murukku 200g: Selling price Rs 50 before 5% GST, MRP Rs 52.50
        product = Product.objects.get(code='PRD-MURUKKU')
        sku = ProductPackSize.objects.get(sku_code='SKU-MRK-200G')
        self.assertEqual(sku.product, product)
        self.assertEqual(sku.retailer_price, Decimal('50.00'))
        self.assertEqual(sku.distributor_price, Decimal('50.00'))
        self.assertEqual(sku.mrp, Decimal('52.50'))
        # 5% GST verification: 50 * 1.05 = 52.50
        self.assertEqual(sku.retailer_price * Decimal('1.05'), sku.mrp)

    def test_exact_bom_specification(self):
        call_command('seed_snacks_benchmark')

        bom = BillOfMaterials.objects.get(bom_code='BOM-MRK-200PKT')
        self.assertEqual(bom.batch_size, Decimal('200.00'))
        self.assertEqual(bom.output_uom.code, 'PCS')
        self.assertEqual(bom.expected_yield_pct, Decimal('100.00'))
        self.assertEqual(bom.expected_output_quantity, Decimal('200.00'))

        # Check BOM constituent ingredients
        items = {bi.raw_material.code if bi.raw_material else bi.packaging_material.code: bi for bi in bom.items.all()}

        # Flour: 40 kg
        self.assertIn('RM-FLOUR', items)
        self.assertEqual(items['RM-FLOUR'].quantity, Decimal('40.0000'))
        self.assertEqual(items['RM-FLOUR'].uom.code, 'KG')

        # Oil: 10 L
        self.assertIn('RM-OIL', items)
        self.assertEqual(items['RM-OIL'].quantity, Decimal('10.0000'))
        self.assertEqual(items['RM-OIL'].uom.code, 'L')

        # Spice mix: 1.2 kg
        self.assertIn('RM-SPICE', items)
        self.assertEqual(items['RM-SPICE'].quantity, Decimal('1.2000'))
        self.assertEqual(items['RM-SPICE'].uom.code, 'KG')

        # Pouches: 200 pcs
        self.assertIn('PM-POUCH', items)
        self.assertEqual(items['PM-POUCH'].quantity, Decimal('200.0000'))
        self.assertEqual(items['PM-POUCH'].uom.code, 'PCS')

        # Cartons: 10 pcs
        self.assertIn('PM-CARTON', items)
        self.assertEqual(items['PM-CARTON'].quantity, Decimal('10.0000'))
        self.assertEqual(items['PM-CARTON'].uom.code, 'PCS')

    def test_exact_flour_purchase_and_grn(self):
        call_command('seed_snacks_benchmark')

        po = PurchaseOrder.objects.get(po_number='PO-BENCH-01')
        po_item = po.items.first()
        self.assertEqual(po_item.raw_material.code, 'RM-FLOUR')
        self.assertEqual(po_item.ordered_quantity, Decimal('60.0000'))
        self.assertEqual(po_item.unit_price, Decimal('45.00'))
        self.assertEqual(po.total_amount, Decimal('2700.00'))

        grn = GoodsReceiptNote.objects.get(grn_number='GRN-BENCH-01')
        self.assertTrue(grn.is_posted)
        grn_item = grn.items.first()
        self.assertEqual(grn_item.accepted_quantity, Decimal('60.0000'))
        self.assertEqual(grn_item.unit_price, Decimal('45.00'))

    def test_stock_balance_equation_opening_plus_receipts_minus_issues_equals_closing(self):
        call_command('seed_snacks_benchmark')

        # Flour: Opening 100 kg (@ Rs 42/kg) + Purchase 60 kg (@ Rs 45/kg) = Closing 160 kg
        flour_stock = StockItem.objects.filter(raw_material__code='RM-FLOUR')
        flour_total = sum(s.quantity_on_hand for s in flour_stock)
        self.assertEqual(flour_total, Decimal('160.0000'))

        # Verify ledger entries for flour
        flour_ledger = StockLedgerEntry.objects.filter(raw_material__code='RM-FLOUR').order_by('id')
        self.assertEqual(flour_ledger.count(), 2)

        op_entry = flour_ledger[0]
        self.assertEqual(op_entry.movement_type, MovementType.OPENING_BALANCE)
        self.assertEqual(op_entry.quantity_change, Decimal('100.0000'))
        self.assertEqual(op_entry.unit_cost, Decimal('42.00'))
        self.assertEqual(op_entry.closing_quantity, Decimal('100.0000'))

        pur_entry = flour_ledger[1]
        self.assertEqual(pur_entry.movement_type, MovementType.PURCHASE_RECEIPT)
        self.assertEqual(pur_entry.quantity_change, Decimal('60.0000'))
        self.assertEqual(pur_entry.unit_cost, Decimal('45.00'))
        self.assertEqual(pur_entry.closing_quantity, Decimal('60.0000'))

        # Aggregate Equation: Opening (100) + Receipts (60) - Issues (0) = Closing (160)
        self.assertEqual(
            op_entry.quantity_change + pur_entry.quantity_change - Decimal('0.0000'),
            flour_total
        )
        self.assertEqual(flour_total, Decimal('160.0000'))

        # Oil: Opening 30 L (@ Rs 140/L) = Closing 30 L
        oil_stock = StockItem.objects.filter(raw_material__code='RM-OIL')
        oil_total = sum(s.quantity_on_hand for s in oil_stock)
        self.assertEqual(oil_total, Decimal('30.0000'))
        oil_entry = StockLedgerEntry.objects.get(raw_material__code='RM-OIL')
        self.assertEqual(oil_entry.unit_cost, Decimal('140.00'))
        self.assertEqual(oil_entry.quantity_change, Decimal('30.0000'))

        # Spice mix: Opening 5 kg (@ Rs 200/kg) = Closing 5 kg
        spice_stock = StockItem.objects.filter(raw_material__code='RM-SPICE')
        spice_total = sum(s.quantity_on_hand for s in spice_stock)
        self.assertEqual(spice_total, Decimal('5.0000'))
        spice_entry = StockLedgerEntry.objects.get(raw_material__code='RM-SPICE')
        self.assertEqual(spice_entry.unit_cost, Decimal('200.00'))
        self.assertEqual(spice_entry.quantity_change, Decimal('5.0000'))

        # Pouches: Opening 500 pcs (@ Rs 2.50/ea) = Closing 500 pcs
        pouch_stock = StockItem.objects.filter(packaging_material__code='PM-POUCH')
        pouch_total = sum(s.quantity_on_hand for s in pouch_stock)
        self.assertEqual(pouch_total, Decimal('500.0000'))
        pouch_entry = StockLedgerEntry.objects.get(packaging_material__code='PM-POUCH')
        self.assertEqual(pouch_entry.unit_cost, Decimal('2.50'))
        self.assertEqual(pouch_entry.quantity_change, Decimal('500.0000'))

        # Cartons: Opening 30 pcs (@ Rs 15/ea, 20 pkts/ctn) = Closing 30 pcs
        carton_stock = StockItem.objects.filter(packaging_material__code='PM-CARTON')
        carton_total = sum(s.quantity_on_hand for s in carton_stock)
        self.assertEqual(carton_total, Decimal('30.0000'))
        carton_entry = StockLedgerEntry.objects.get(packaging_material__code='PM-CARTON')
        self.assertEqual(carton_entry.unit_cost, Decimal('15.00'))
        self.assertEqual(carton_entry.quantity_change, Decimal('30.0000'))

        # Finished Murukku 200g: Opening 50 packets = Closing 50 packets
        fg_stock = StockItem.objects.filter(product_pack_size__sku_code='SKU-MRK-200G')
        fg_total = sum(s.quantity_on_hand for s in fg_stock)
        self.assertEqual(fg_total, Decimal('50.0000'))
        fg_entry = StockLedgerEntry.objects.get(product_pack_size__sku_code='SKU-MRK-200G')
        self.assertEqual(fg_entry.quantity_change, Decimal('50.0000'))

    def test_idempotency_no_duplicate_records(self):
        # Execute seed twice
        call_command('seed_snacks_benchmark')
        call_command('seed_snacks_benchmark')

        # Assert no duplicate documents
        self.assertEqual(PurchaseOrder.objects.filter(po_number='PO-BENCH-01').count(), 1)
        self.assertEqual(GoodsReceiptNote.objects.filter(grn_number='GRN-BENCH-01').count(), 1)
        self.assertEqual(BillOfMaterials.objects.filter(bom_code='BOM-MRK-200PKT').count(), 1)
        self.assertEqual(ProductPackSize.objects.filter(sku_code='SKU-MRK-200G').count(), 1)

        # Assert exactly 7 stock ledger entries (6 opening + 1 purchase receipt)
        self.assertEqual(StockLedgerEntry.objects.count(), 7)

        # Quantities on hand remain exactly identical after re-run
        self.assertEqual(
            sum(s.quantity_on_hand for s in StockItem.objects.filter(raw_material__code='RM-FLOUR')),
            Decimal('160.0000')
        )
        self.assertEqual(
            sum(s.quantity_on_hand for s in StockItem.objects.filter(raw_material__code='RM-OIL')),
            Decimal('30.0000')
        )
        self.assertEqual(
            sum(s.quantity_on_hand for s in StockItem.objects.filter(raw_material__code='RM-SPICE')),
            Decimal('5.0000')
        )
        self.assertEqual(
            sum(s.quantity_on_hand for s in StockItem.objects.filter(packaging_material__code='PM-POUCH')),
            Decimal('500.0000')
        )
        self.assertEqual(
            sum(s.quantity_on_hand for s in StockItem.objects.filter(packaging_material__code='PM-CARTON')),
            Decimal('30.0000')
        )
        self.assertEqual(
            sum(s.quantity_on_hand for s in StockItem.objects.filter(product_pack_size__sku_code='SKU-MRK-200G')),
            Decimal('50.0000')
        )
