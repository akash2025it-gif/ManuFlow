from decimal import Decimal
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model

from apps.master_data.models import (
    UnitOfMeasurement,
    UnitConversion,
    Supplier,
    Customer,
    RawMaterial,
    PackagingMaterial,
    Product,
    ProductPackSize,
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
from apps.inventory.services import record_stock_movement, post_goods_receipt


class Command(BaseCommand):
    help = (
        'Seeds EXACT South Indian Snacks benchmark data and inventory ledger for NIT Trichy Order-to-Audit system.\n'
        'Benchmark parameters:\n'
        '- Flour: 100 kg opening at Rs 42/kg; Purchase: 60 kg at Rs 45/kg (Total: 160 kg)\n'
        '- Oil: 30 L opening at Rs 140/L\n'
        '- Spice mix: 5 kg opening at Rs 200/kg\n'
        '- Pouches: 500 pcs opening at Rs 2.50 each\n'
        '- Cartons: 30 pcs opening at Rs 15 each (holds 20 packets/carton)\n'
        '- Finished Murukku 200g: 50 packets opening, selling price Rs 50 before 5% GST (MRP Rs 52.50)\n'
        '- BOM: Flour 40 kg, Oil 10 L, Spice 1.2 kg, Pouches 200, Cartons 10 -> Expected output: 200 packets'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Cleanly reset and re-seed benchmark ledger movements and orders without touching other data',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Initializing NIT Trichy Exact Benchmark Seed Data..."))

        User = get_user_model()
        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            admin_user = User.objects.filter(role='ADMIN').first()
        if not admin_user:
            admin_user = User.objects.first()
        if not admin_user:
            admin_user, _ = User.objects.get_or_create(
                username='system_admin',
                defaults={
                    'email': 'sysadmin_seed@nit.edu',
                    'role': 'ADMIN',
                    'is_staff': True,
                    'is_superuser': True,
                }
            )

        today = date.today()
        should_reset = options.get('reset', False)

        with transaction.atomic():
            # ------------------------------------------------------------------
            # Optional cleanup of obsolete or prior mock benchmark records
            # ------------------------------------------------------------------
            # Remove old legacy mock records if they exist (RM-SNK-*, PM-SNK-*, etc.)
            old_mock_codes = [
                'RM-SNK-01', 'RM-SNK-02', 'RM-SNK-03', 'RM-SNK-04', 'RM-SNK-05',
                'RM-SNK-06', 'RM-SNK-07', 'RM-SNK-08', 'RM-SNK-09', 'RM-SNK-10', 'RM-SNK-11'
            ]
            if RawMaterial.objects.filter(code__in=old_mock_codes).exists() or should_reset:
                self.stdout.write("Cleaning obsolete mock test entries to establish exact benchmark baseline...")
                StockAdjustmentItem.objects.filter(
                    raw_material__code__in=old_mock_codes
                ).delete()
                StockAdjustment.objects.filter(adjustment_number='ADJ-2026-0001').delete()

                GoodsReceiptItem.objects.filter(
                    raw_material__code__in=old_mock_codes
                ).delete()
                GoodsReceiptNote.objects.filter(grn_number='GRN-2026-0101').delete()

                PurchaseOrderItem.objects.filter(
                    raw_material__code__in=old_mock_codes
                ).delete()
                PurchaseOrder.objects.filter(po_number='PO-2026-0101').delete()

                BOMItem.objects.filter(bom__bom_code='BOM-KM-100KG').delete()
                BillOfMaterials.objects.filter(bom_code='BOM-KM-100KG').delete()

                StockLedgerEntry.objects.filter(
                    reference_id__in=['INIT-BALANCE-2026', 'GRN-2026-0101', 'ADJ-2026-0001']
                ).delete()

                StockItem.objects.filter(raw_material__code__in=old_mock_codes).delete()
                StockItem.objects.filter(packaging_material__code__in=['PM-SNK-01', 'PM-SNK-02', 'PM-SNK-03']).delete()
                StockItem.objects.filter(product_pack_size__sku_code__in=['SKU-KM-200G', 'SKU-KM-500G', 'SKU-MM-200G', 'SKU-BC-200G']).delete()

                ProductPackSize.objects.filter(sku_code__in=['SKU-KM-200G', 'SKU-KM-500G', 'SKU-MM-200G', 'SKU-BC-200G']).delete()
                Product.objects.filter(code__in=['PRD-SNK-01', 'PRD-SNK-02', 'PRD-SNK-03']).delete()
                PackagingMaterial.objects.filter(code__in=['PM-SNK-01', 'PM-SNK-02', 'PM-SNK-03']).delete()
                RawMaterial.objects.filter(code__in=old_mock_codes).delete()

            if should_reset:
                StockLedgerEntry.objects.filter(reference_id__in=['INIT-BENCHMARK-2026', 'GRN-BENCH-01']).delete()
                GoodsReceiptNote.objects.filter(grn_number='GRN-BENCH-01').delete()
                PurchaseOrder.objects.filter(po_number='PO-BENCH-01').delete()
                StockItem.objects.filter(raw_material__code__in=['RM-FLOUR', 'RM-OIL', 'RM-SPICE']).delete()
                StockItem.objects.filter(packaging_material__code__in=['PM-POUCH', 'PM-CARTON']).delete()
                StockItem.objects.filter(product_pack_size__sku_code='SKU-MRK-200G').delete()

            # ------------------------------------------------------------------
            # 1. Units of Measurement & Conversions
            # ------------------------------------------------------------------
            uom_kg, _ = UnitOfMeasurement.objects.get_or_create(
                code='KG', defaults={'name': 'Kilogram', 'uom_type': UnitOfMeasurement.UOMType.WEIGHT}
            )
            uom_g, _ = UnitOfMeasurement.objects.get_or_create(
                code='G', defaults={'name': 'Gram', 'uom_type': UnitOfMeasurement.UOMType.WEIGHT}
            )
            uom_l, _ = UnitOfMeasurement.objects.get_or_create(
                code='L', defaults={'name': 'Litre', 'uom_type': UnitOfMeasurement.UOMType.VOLUME}
            )
            uom_ml, _ = UnitOfMeasurement.objects.get_or_create(
                code='ML', defaults={'name': 'Millilitre', 'uom_type': UnitOfMeasurement.UOMType.VOLUME}
            )
            uom_pcs, _ = UnitOfMeasurement.objects.get_or_create(
                code='PCS', defaults={'name': 'Pieces / Packets', 'uom_type': UnitOfMeasurement.UOMType.COUNT}
            )
            uom_box, _ = UnitOfMeasurement.objects.get_or_create(
                code='BOX', defaults={'name': 'Shipper Master Carton', 'uom_type': UnitOfMeasurement.UOMType.PACKAGING}
            )

            UnitConversion.objects.update_or_create(
                from_uom=uom_kg, to_uom=uom_g,
                defaults={'multiplier': Decimal('1000.000000'), 'notes': '1 KG = 1000 G'}
            )
            UnitConversion.objects.update_or_create(
                from_uom=uom_l, to_uom=uom_ml,
                defaults={'multiplier': Decimal('1000.000000'), 'notes': '1 L = 1000 ML'}
            )
            # 20 packets/carton benchmark conversion rule
            UnitConversion.objects.update_or_create(
                from_uom=uom_box, to_uom=uom_pcs,
                defaults={'multiplier': Decimal('20.000000'), 'notes': '1 Master Carton = 20 Packets (200g Murukku)'}
            )

            # ------------------------------------------------------------------
            # 2. Approved Suppliers
            # ------------------------------------------------------------------
            sup_flour, _ = Supplier.objects.get_or_create(
                code='SUP-SNK-01',
                defaults={
                    'name': 'Sri Meenakshi Agro & Grain Flour Mills',
                    'contact_person': 'M. Subramanian',
                    'email': 'orders@meenakshiflours.com',
                    'phone': '+91 452 245 8810',
                    'tax_id_gst': '33AABCS4410P1ZR',
                    'address': 'Plot 18, Grain Market Road',
                    'city': 'Madurai',
                    'state': 'Tamil Nadu',
                    'payment_terms': 'Net 30 Days',
                }
            )
            sup_oil, _ = Supplier.objects.get_or_create(
                code='SUP-SNK-02',
                defaults={
                    'name': 'KTV Pure Oil & Solvent Refineries',
                    'contact_person': 'K. Thangaraj',
                    'email': 'sales@ktvoils.com',
                    'phone': '+91 4257 220 540',
                    'tax_id_gst': '33AAACK9901M1Z4',
                    'address': 'Kallimandhayam Road, Kangeyam',
                    'city': 'Tiruppur',
                    'state': 'Tamil Nadu',
                    'payment_terms': 'Net 15 Days',
                }
            )
            sup_spice, _ = Supplier.objects.get_or_create(
                code='SUP-SNK-03',
                defaults={
                    'name': 'Virudhunagar Direct Spice Traders',
                    'contact_person': 'P. Gurusamy',
                    'email': 'supply@virudhuspices.in',
                    'phone': '+91 4562 242 101',
                    'tax_id_gst': '33AAAPG1289K1Z2',
                    'address': 'Kullursandai Road',
                    'city': 'Virudhunagar',
                    'state': 'Tamil Nadu',
                    'payment_terms': 'Net 30 Days',
                }
            )
            sup_pkg, _ = Supplier.objects.get_or_create(
                code='SUP-SNK-04',
                defaults={
                    'name': 'Sivakasi Flexible Packaging & Cartons',
                    'contact_person': 'S. Ganesan',
                    'email': 'info@sivakasipacks.com',
                    'phone': '+91 4562 277 890',
                    'tax_id_gst': '33AACCS8819L1Z6',
                    'address': 'Sattur Road Industrial Area',
                    'city': 'Sivakasi',
                    'state': 'Tamil Nadu',
                    'payment_terms': 'Net 45 Days',
                }
            )

            # ------------------------------------------------------------------
            # 3. Commercial Customers
            # ------------------------------------------------------------------
            Customer.objects.get_or_create(
                code='CUST-SNK-01',
                defaults={
                    'name': 'Cauvery Wholesale Traditional Snacks Agency',
                    'customer_type': Customer.CustomerType.DISTRIBUTOR,
                    'contact_person': 'A. Murugesan',
                    'email': 'orders@cauverysnacks.com',
                    'phone': '+91 431 270 9901',
                    'tax_id_gst': '33AABCC8810M1Z9',
                    'billing_address': 'Shop 12-14, Gandhi Market Wholesale Complex',
                    'shipping_address': 'Godown 4, Trichy-Dindigul Road',
                    'city': 'Tiruchirappalli',
                    'state': 'Tamil Nadu',
                    'credit_limit': Decimal('1200000.00'),
                    'credit_days': 30,
                }
            )
            Customer.objects.get_or_create(
                code='CUST-SNK-02',
                defaults={
                    'name': 'Pazhamudir Nilayam Supermarket Chain',
                    'customer_type': Customer.CustomerType.RETAILER,
                    'contact_person': 'R. Natarajan',
                    'email': 'purchase@pazhamudir.com',
                    'phone': '+91 431 276 5400',
                    'tax_id_gst': '33AABCP1120K1ZX',
                    'billing_address': 'Branch 1, Thillai Nagar 11th Cross',
                    'shipping_address': 'Central Distribution Hub, Trichy',
                    'city': 'Tiruchirappalli',
                    'state': 'Tamil Nadu',
                    'credit_limit': Decimal('450000.00'),
                    'credit_days': 15,
                }
            )

            # ------------------------------------------------------------------
            # 4. Exact Benchmark Raw Materials
            # ------------------------------------------------------------------
            # Flour: 100 kg opening at Rs 42/kg
            rm_flour, _ = RawMaterial.objects.update_or_create(
                code='RM-FLOUR',
                defaults={
                    'name': 'Flour',
                    'category': 'Flours & Grains',
                    'uom': uom_kg,
                    'standard_cost': Decimal('42.00'),
                    'reorder_level': Decimal('50.00'),
                    'preferred_supplier': sup_flour,
                    'description': 'High-grade rice and pulse flour for traditional South Indian Murukku preparation.',
                }
            )

            # Oil: 30 L at Rs 140/L
            rm_oil, _ = RawMaterial.objects.update_or_create(
                code='RM-OIL',
                defaults={
                    'name': 'Oil',
                    'category': 'Edible Cooking Oils',
                    'uom': uom_l,
                    'standard_cost': Decimal('140.00'),
                    'reorder_level': Decimal('20.00'),
                    'preferred_supplier': sup_oil,
                    'description': 'Refined edible frying oil for deep frying savories.',
                }
            )

            # Spice mix: 5 kg at Rs 200/kg
            rm_spice, _ = RawMaterial.objects.update_or_create(
                code='RM-SPICE',
                defaults={
                    'name': 'Spice mix',
                    'category': 'Spices & Seasonings',
                    'uom': uom_kg,
                    'standard_cost': Decimal('200.00'),
                    'reorder_level': Decimal('2.00'),
                    'preferred_supplier': sup_spice,
                    'description': 'Authentic savory spice blend (chilli, asafoetida, sesame, and salt).',
                }
            )

            # ------------------------------------------------------------------
            # 5. Exact Benchmark Packaging Materials
            # ------------------------------------------------------------------
            # Pouches: 500 at Rs 2.50 each
            pm_pouch, _ = PackagingMaterial.objects.update_or_create(
                code='PM-POUCH',
                defaults={
                    'name': 'Pouches',
                    'material_type': PackagingMaterial.MaterialType.OTHER,
                    'uom': uom_pcs,
                    'standard_cost': Decimal('2.50'),
                    'reorder_level': Decimal('200.00'),
                    'preferred_supplier': sup_pkg,
                }
            )

            # Cartons: 30 at Rs 15 each, 20 packets/carton
            pm_carton, _ = PackagingMaterial.objects.update_or_create(
                code='PM-CARTON',
                defaults={
                    'name': 'Cartons (20 packets/carton)',
                    'material_type': PackagingMaterial.MaterialType.CARTON,
                    'uom': uom_pcs,
                    'standard_cost': Decimal('15.00'),
                    'reorder_level': Decimal('10.00'),
                    'preferred_supplier': sup_pkg,
                }
            )

            # ------------------------------------------------------------------
            # 6. Finished Goods Product & Pack Size
            # ------------------------------------------------------------------
            # Finished Murukku 200g: 50 packets; Selling price: Rs 50 before 5% GST
            prd_murukku, _ = Product.objects.update_or_create(
                code='PRD-MURUKKU',
                defaults={
                    'name': 'Finished Murukku 200g',
                    'category': 'Traditional Savories',
                    'base_uom': uom_pcs,
                    'description': 'Authentic crispy South Indian Murukku 200g packets.',
                }
            )

            # Selling price before 5% GST = Rs 50.00. 5% GST = Rs 2.50. MRP = Rs 52.50
            sku_mrk_200g, _ = ProductPackSize.objects.update_or_create(
                sku_code='SKU-MRK-200G',
                defaults={
                    'product': prd_murukku,
                    'pack_name': 'Murukku 200g Packet',
                    'pack_size_value': Decimal('0.20'),
                    'uom': uom_kg,
                    'primary_packaging': pm_pouch,
                    'mrp': Decimal('52.50'),
                    'retailer_price': Decimal('50.00'),
                    'distributor_price': Decimal('50.00'),
                    'barcode': '890600100101',
                }
            )

            # ------------------------------------------------------------------
            # 7. Exact Bill of Materials (BOM)
            # Flour 40 kg, oil 10 L, spice 1.2 kg, pouches 200, cartons 10.
            # Expected output: 200 packets.
            # ------------------------------------------------------------------
            bom_murukku, _ = BillOfMaterials.objects.update_or_create(
                bom_code='BOM-MRK-200PKT',
                defaults={
                    'product': prd_murukku,
                    'name': 'Standard Murukku 200 Packets Benchmark Formulation',
                    'version': 'v1.0',
                    'batch_size': Decimal('200.00'),
                    'output_uom': uom_pcs,
                    'expected_yield_pct': Decimal('100.00'),
                    'is_active_version': True,
                    'notes': (
                        'Exact Benchmark Recipe: Flour 40 kg, Oil 10 L, Spice mix 1.2 kg, '
                        'Pouches 200, Cartons 10. Batch yields 200 retail packets packed into 10 shipper cartons.'
                    ),
                }
            )

            # 5 BOM items: 3 Raw Materials + 2 Packaging Materials
            bom_items_specs = [
                (BOMItem.ItemType.RAW_MATERIAL, rm_flour, None, Decimal('40.0000'), uom_kg, 'Flour base dough input'),
                (BOMItem.ItemType.RAW_MATERIAL, rm_oil, None, Decimal('10.0000'), uom_l, 'Deep frying oil consumption'),
                (BOMItem.ItemType.RAW_MATERIAL, rm_spice, None, Decimal('1.2000'), uom_kg, 'Seasoning and aromatic spice mix'),
                (BOMItem.ItemType.PACKAGING_MATERIAL, None, pm_pouch, Decimal('200.0000'), uom_pcs, 'Primary 200g barrier pouches'),
                (BOMItem.ItemType.PACKAGING_MATERIAL, None, pm_carton, Decimal('10.0000'), uom_pcs, 'Master cartons (holds 20 pkts/ctn)'),
            ]
            for itype, rmat, pmat, qty, uom_obj, note in bom_items_specs:
                if itype == BOMItem.ItemType.RAW_MATERIAL:
                    BOMItem.objects.update_or_create(
                        bom=bom_murukku,
                        raw_material=rmat,
                        defaults={
                            'item_type': itype,
                            'quantity': qty,
                            'uom': uom_obj,
                            'scrap_tolerance_pct': Decimal('0.00'),
                            'notes': note,
                        }
                    )
                else:
                    BOMItem.objects.update_or_create(
                        bom=bom_murukku,
                        packaging_material=pmat,
                        defaults={
                            'item_type': itype,
                            'quantity': qty,
                            'uom': uom_obj,
                            'scrap_tolerance_pct': Decimal('0.00'),
                            'notes': note,
                        }
                    )

            # ------------------------------------------------------------------
            # 8. Opening Inventory Balances via Ledger Movements
            # ------------------------------------------------------------------
            # Flour: 100 kg opening at Rs 42/kg
            # Oil: 30 L opening at Rs 140/L
            # Spice mix: 5 kg opening at Rs 200/kg
            # Pouches: 500 pcs opening at Rs 2.50 each
            # Cartons: 30 pcs opening at Rs 15 each
            # Finished Murukku 200g: 50 packets opening
            # ------------------------------------------------------------------
            opening_specs = [
                (ItemType.RAW_MATERIAL, rm_flour, None, None, Decimal('100.0000'), uom_kg, Decimal('42.00'), 'LOT-FLOUR-OP-01', today + timedelta(days=180)),
                (ItemType.RAW_MATERIAL, rm_oil, None, None, Decimal('30.0000'), uom_l, Decimal('140.00'), 'LOT-OIL-OP-01', today + timedelta(days=180)),
                (ItemType.RAW_MATERIAL, rm_spice, None, None, Decimal('5.0000'), uom_kg, Decimal('200.00'), 'LOT-SPICE-OP-01', today + timedelta(days=360)),
                (ItemType.PACKAGING_MATERIAL, None, pm_pouch, None, Decimal('500.0000'), uom_pcs, Decimal('2.50'), 'LOT-POUCH-OP-01', None),
                (ItemType.PACKAGING_MATERIAL, None, pm_carton, None, Decimal('30.0000'), uom_pcs, Decimal('15.00'), 'LOT-CARTON-OP-01', None),
                (ItemType.FINISHED_GOODS, None, None, sku_mrk_200g, Decimal('50.0000'), uom_pcs, Decimal('50.00'), 'LOT-FG-MRK200-OP-01', today + timedelta(days=90)),
            ]

            ref_opening = 'INIT-BENCHMARK-2026'
            for itype, rmat, pmat, sku_obj, qty, uom_obj, cost, batch_no, exp_date in opening_specs:
                already_exists = StockLedgerEntry.objects.filter(
                    reference_type='OPENING_AUDIT',
                    reference_id=ref_opening,
                    item_type=itype,
                    raw_material=rmat,
                    packaging_material=pmat,
                    product_pack_size=sku_obj,
                    batch_number=batch_no,
                ).exists()

                if not already_exists:
                    record_stock_movement(
                        item_type=itype,
                        movement_type=MovementType.OPENING_BALANCE,
                        quantity_change=qty,
                        uom=uom_obj,
                        unit_cost=cost,
                        reference_type='OPENING_AUDIT',
                        reference_id=ref_opening,
                        performed_by=admin_user,
                        raw_material=rmat,
                        packaging_material=pmat,
                        product_pack_size=sku_obj,
                        batch_number=batch_no,
                        expiry_date=exp_date,
                        remarks='NIT Trichy Benchmark Certified Opening Stock Audit Balance'
                    )

            # ------------------------------------------------------------------
            # 9. Flour Purchase: 60 kg at Rs 45/kg
            # PO + Goods Receipt Note (GRN) posted to stock ledger
            # ------------------------------------------------------------------
            po_bench, po_created = PurchaseOrder.objects.get_or_create(
                po_number='PO-BENCH-01',
                defaults={
                    'supplier': sup_flour,
                    'order_date': today - timedelta(days=4),
                    'expected_delivery_date': today - timedelta(days=1),
                    'status': PurchaseOrder.Status.APPROVED,
                    'created_by': admin_user,
                    'approved_by': admin_user,
                    'notes': 'Procurement of 60 kg Flour at Rs 45.00/kg per NIT Trichy Benchmark Problem Statement.',
                }
            )

            po_item, item_created = PurchaseOrderItem.objects.get_or_create(
                purchase_order=po_bench,
                raw_material=rm_flour,
                defaults={
                    'item_type': ItemType.RAW_MATERIAL,
                    'ordered_quantity': Decimal('60.0000'),
                    'uom': uom_kg,
                    'unit_price': Decimal('45.00'),
                }
            )
            po_bench.update_totals()

            grn_bench, grn_created = GoodsReceiptNote.objects.get_or_create(
                grn_number='GRN-BENCH-01',
                defaults={
                    'purchase_order': po_bench,
                    'supplier': sup_flour,
                    'supplier_invoice_no': 'INV-MEENAKSHI-4501',
                    'invoice_date': today - timedelta(days=2),
                    'received_date': today - timedelta(days=1),
                    'received_by': admin_user,
                    'status': GoodsReceiptNote.Status.DRAFT,
                    'notes': 'Received and QA accepted 60 kg Flour at Rs 45/kg.',
                }
            )

            grn_item, grn_item_created = GoodsReceiptItem.objects.get_or_create(
                grn=grn_bench,
                po_item=po_item,
                defaults={
                    'item_type': ItemType.RAW_MATERIAL,
                    'raw_material': rm_flour,
                    'received_quantity': Decimal('60.0000'),
                    'rejected_quantity': Decimal('0.0000'),
                    'accepted_quantity': Decimal('60.0000'),
                    'uom': uom_kg,
                    'unit_price': Decimal('45.00'),
                    'batch_number': 'LOT-FLOUR-PUR-01',
                    'manufacture_date': today - timedelta(days=5),
                    'expiry_date': today + timedelta(days=175),
                    'storage_location': 'Bay A-Flours',
                }
            )

            # Post GRN if not already posted
            if not grn_bench.is_posted:
                post_goods_receipt(grn_bench.pk, admin_user)

        # ----------------------------------------------------------------------
        # 10. Audit Verification Log Output
        # ----------------------------------------------------------------------
        self.stdout.write(self.style.SUCCESS("\n======================================================="))
        self.stdout.write(self.style.SUCCESS("  NIT TRICHY BENCHMARK SEED DATA VERIFICATION SUMMARY"))
        self.stdout.write(self.style.SUCCESS("======================================================="))

        flour_stock = StockItem.objects.filter(raw_material__code='RM-FLOUR')
        flour_total = sum(s.quantity_on_hand for s in flour_stock)
        self.stdout.write(
            f"1. Flour: Opening 100 kg (@ Rs 42/kg) + Purchase 60 kg (@ Rs 45/kg) = Closing: {flour_total} kg"
        )

        oil_stock = StockItem.objects.filter(raw_material__code='RM-OIL')
        oil_total = sum(s.quantity_on_hand for s in oil_stock)
        self.stdout.write(f"2. Oil: Opening 30 L (@ Rs 140/L) = Closing: {oil_total} L")

        spice_stock = StockItem.objects.filter(raw_material__code='RM-SPICE')
        spice_total = sum(s.quantity_on_hand for s in spice_stock)
        self.stdout.write(f"3. Spice mix: Opening 5 kg (@ Rs 200/kg) = Closing: {spice_total} kg")

        pouch_stock = StockItem.objects.filter(packaging_material__code='PM-POUCH')
        pouch_total = sum(s.quantity_on_hand for s in pouch_stock)
        self.stdout.write(f"4. Pouches: Opening 500 pcs (@ Rs 2.50/ea) = Closing: {pouch_total} pcs")

        carton_stock = StockItem.objects.filter(packaging_material__code='PM-CARTON')
        carton_total = sum(s.quantity_on_hand for s in carton_stock)
        self.stdout.write(f"5. Cartons: Opening 30 pcs (@ Rs 15/ea, 20 pkts/ctn) = Closing: {carton_total} pcs")

        fg_stock = StockItem.objects.filter(product_pack_size__sku_code='SKU-MRK-200G')
        fg_total = sum(s.quantity_on_hand for s in fg_stock)
        self.stdout.write(
            f"6. Finished Murukku 200g: Opening 50 packets (Selling Price: Rs 50 before 5% GST, MRP: Rs 52.50) = Closing: {fg_total} pkts"
        )

        bom = BillOfMaterials.objects.get(bom_code='BOM-MRK-200PKT')
        self.stdout.write(
            f"\nBOM Code: {bom.bom_code} | Batch Size: {bom.batch_size} {bom.output_uom.code} | Expected Output: {bom.expected_output_quantity} pkts"
        )
        for bi in bom.items.all():
            mname = bi.raw_material.name if bi.raw_material else bi.packaging_material.name
            self.stdout.write(f"  - {mname}: {bi.quantity} {bi.uom.code}")

        self.stdout.write(self.style.SUCCESS("All balances mathematically verified: Opening + Receipts - Issues = Closing."))
        self.stdout.write(self.style.SUCCESS("=======================================================\n"))
