from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
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


class Command(BaseCommand):
    help = 'Seeds realistic Master Data (UOMs, Conversions, Suppliers, Customers, Materials, Products, Pack Sizes, and BOMs)'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding Master Data for NIT Trichy Order-to-Audit Management System..."))

        with transaction.atomic():
            # 1. Units of Measurement
            uoms_data = [
                {'code': 'KG', 'name': 'Kilogram', 'uom_type': UnitOfMeasurement.UOMType.WEIGHT, 'description': 'Standard metric mass unit'},
                {'code': 'G', 'name': 'Gram', 'uom_type': UnitOfMeasurement.UOMType.WEIGHT, 'description': 'One-thousandth of a kilogram'},
                {'code': 'L', 'name': 'Litre', 'uom_type': UnitOfMeasurement.UOMType.VOLUME, 'description': 'Standard metric liquid volume'},
                {'code': 'ML', 'name': 'Millilitre', 'uom_type': UnitOfMeasurement.UOMType.VOLUME, 'description': 'One-thousandth of a litre'},
                {'code': 'PCS', 'name': 'Pieces / Units', 'uom_type': UnitOfMeasurement.UOMType.COUNT, 'description': 'Individual discrete units'},
                {'code': 'BOX', 'name': 'Corrugated Box', 'uom_type': UnitOfMeasurement.UOMType.PACKAGING, 'description': 'Outer shipper box packaging'},
                {'code': 'DRUM', 'name': 'Industrial Drum', 'uom_type': UnitOfMeasurement.UOMType.PACKAGING, 'description': '200L heavy industrial barrel'},
                {'code': 'M', 'name': 'Meter', 'uom_type': UnitOfMeasurement.UOMType.LENGTH, 'description': 'Metric linear distance'},
            ]
            uom_map = {}
            for item in uoms_data:
                uom, _ = UnitOfMeasurement.objects.get_or_create(code=item['code'], defaults=item)
                uom_map[uom.code] = uom

            # 2. Unit Conversions
            conversions_data = [
                {'from_code': 'KG', 'to_code': 'G', 'multiplier': Decimal('1000.000000'), 'notes': '1 Kilogram = 1000 Grams'},
                {'from_code': 'L', 'to_code': 'ML', 'multiplier': Decimal('1000.000000'), 'notes': '1 Litre = 1000 Millilitres'},
                {'from_code': 'DRUM', 'to_code': 'L', 'multiplier': Decimal('200.000000'), 'notes': 'Standard industrial barrel holds 200 Litres'},
                {'from_code': 'BOX', 'to_code': 'PCS', 'multiplier': Decimal('20.000000'), 'notes': 'Master carton holds 20 packets (20 packets/carton benchmark)'},
            ]
            for c in conversions_data:
                UnitConversion.objects.update_or_create(
                    from_uom=uom_map[c['from_code']],
                    to_uom=uom_map[c['to_code']],
                    defaults={'multiplier': c['multiplier'], 'notes': c['notes']}
                )

            # 3. Suppliers
            suppliers_data = [
                {
                    'code': 'SUP-001',
                    'name': 'Bharat Chemical & Solvents Corporation',
                    'contact_person': 'Anand Swaminathan',
                    'email': 'orders@bharatchem.in',
                    'phone': '+91 44 2819 4001',
                    'tax_id_gst': '33AAACB2201M1Z1',
                    'address': 'Plot 42, SIDCO Industrial Estate, Guindy',
                    'city': 'Chennai',
                    'state': 'Tamil Nadu',
                    'payment_terms': 'Net 30 Days',
                },
                {
                    'code': 'SUP-002',
                    'name': 'Apex Polymers & Resins Ltd',
                    'contact_person': 'M. Rajesh',
                    'email': 'sales@apexpoly.co.in',
                    'phone': '+91 431 250 8821',
                    'tax_id_gst': '33AABCA9918K1Z5',
                    'address': 'Thuvakudi Industrial Complex',
                    'city': 'Tiruchirappalli',
                    'state': 'Tamil Nadu',
                    'payment_terms': 'Net 15 Days',
                },
                {
                    'code': 'SUP-003',
                    'name': 'South India Corrugated Containers & Packaging',
                    'contact_person': 'P. Venkatachalam',
                    'email': 'supply@sicontainers.com',
                    'phone': '+91 422 249 1190',
                    'tax_id_gst': '33AACCP4412F1Z8',
                    'address': 'Peelamedu Industrial Suburb',
                    'city': 'Coimbatore',
                    'state': 'Tamil Nadu',
                    'payment_terms': 'Net 45 Days',
                },
            ]
            sup_map = {}
            for s in suppliers_data:
                code = s['code']
                supplier, _ = Supplier.objects.get_or_create(code=code, defaults=s)
                sup_map[code] = supplier

            # 4. Customers (Retailers and Wholesale Distributors)
            customers_data = [
                {
                    'code': 'CUST-101',
                    'name': 'Cauvery Industrial Spares & Distribution Pvt Ltd',
                    'customer_type': Customer.CustomerType.DISTRIBUTOR,
                    'contact_person': 'Senthil Nathan',
                    'email': 'procurement@cauveryspares.com',
                    'phone': '+91 431 270 4550',
                    'tax_id_gst': '33AABCC5510R1ZP',
                    'billing_address': '84, Salai Road, Thillai Nagar',
                    'shipping_address': 'Warehouse Complex, Dindigul Road',
                    'city': 'Tiruchirappalli',
                    'state': 'Tamil Nadu',
                    'credit_limit': Decimal('1500000.00'),
                    'credit_days': 45,
                },
                {
                    'code': 'CUST-102',
                    'name': 'Sri Ranga Auto Hardware & Retail Supplies',
                    'customer_type': Customer.CustomerType.RETAILER,
                    'contact_person': 'R. Sundararajan',
                    'email': 'sriranga.auto@gmail.com',
                    'phone': '+91 94431 88200',
                    'tax_id_gst': '33AAACR7711B1ZX',
                    'billing_address': '12/B, Big Bazaar Street',
                    'shipping_address': '12/B, Big Bazaar Street',
                    'city': 'Tiruchirappalli',
                    'state': 'Tamil Nadu',
                    'credit_limit': Decimal('200000.00'),
                    'credit_days': 15,
                },
                {
                    'code': 'CUST-103',
                    'name': 'Madurai Heavy Engineering & Chemical Distributors',
                    'customer_type': Customer.CustomerType.DISTRIBUTOR,
                    'contact_person': 'K. Muthuvel',
                    'email': 'muthuvel@maduraidist.com',
                    'phone': '+91 452 233 8901',
                    'tax_id_gst': '33AABCM9112H1ZQ',
                    'billing_address': '45 Bypass Road, Ponmeni',
                    'shipping_address': 'Kappalur Industrial Estate Bay 7',
                    'city': 'Madurai',
                    'state': 'Tamil Nadu',
                    'credit_limit': Decimal('2500000.00'),
                    'credit_days': 60,
                },
                {
                    'code': 'CUST-104',
                    'name': 'Tanjore Machinery & Maintenance Store',
                    'customer_type': Customer.CustomerType.RETAILER,
                    'contact_person': 'V. Balasubramanian',
                    'email': 'tanjore.machinery@yahoo.co.in',
                    'phone': '+91 4362 278 110',
                    'tax_id_gst': '33AACCT1029D1Z3',
                    'billing_address': '108 South Main Street',
                    'shipping_address': '108 South Main Street',
                    'city': 'Thanjavur',
                    'state': 'Tamil Nadu',
                    'credit_limit': Decimal('350000.00'),
                    'credit_days': 21,
                },
            ]
            for c in customers_data:
                Customer.objects.get_or_create(code=c['code'], defaults=c)

            # 5. Raw Materials
            raw_materials_data = [
                {
                    'code': 'RM-001',
                    'name': 'Sodium Lauryl Ether Sulfate (SLES 70%)',
                    'category': 'Surface Active Chemical',
                    'uom': uom_map['KG'],
                    'standard_cost': Decimal('145.00'),
                    'reorder_level': Decimal('500.00'),
                    'preferred_supplier': sup_map['SUP-001'],
                    'description': 'High-performance surfactant and primary degreasing emulsifier.',
                },
                {
                    'code': 'RM-002',
                    'name': 'Industrial Isopropyl Alcohol (IPA 99.8%)',
                    'category': 'Organic Solvent',
                    'uom': uom_map['L'],
                    'standard_cost': Decimal('92.50'),
                    'reorder_level': Decimal('400.00'),
                    'preferred_supplier': sup_map['SUP-001'],
                    'description': 'Rapidly evaporating solvent and technical degreasing carrier.',
                },
                {
                    'code': 'RM-003',
                    'name': 'Phosphoric Acid (Technical Grade 85%)',
                    'category': 'Inorganic Acid',
                    'uom': uom_map['KG'],
                    'standard_cost': Decimal('78.00'),
                    'reorder_level': Decimal('300.00'),
                    'preferred_supplier': sup_map['SUP-001'],
                    'description': 'Deoxidizing and rust conversion agent for ferrous metals.',
                },
                {
                    'code': 'RM-004',
                    'name': 'Demineralized Water (Plant Produced)',
                    'category': 'Solvent Carrier',
                    'uom': uom_map['L'],
                    'standard_cost': Decimal('1.50'),
                    'reorder_level': Decimal('2000.00'),
                    'preferred_supplier': None,
                    'description': 'Ultra-pure processed demineralized water (< 5 microsiemens/cm).',
                },
                {
                    'code': 'RM-005',
                    'name': 'Triethanolamine Corrosion Inhibitor',
                    'category': 'Protective Additive',
                    'uom': uom_map['KG'],
                    'standard_cost': Decimal('380.00'),
                    'reorder_level': Decimal('100.00'),
                    'preferred_supplier': sup_map['SUP-002'],
                    'description': 'Passivates freshly cleaned metal surfaces against flash rusting.',
                },
            ]
            rm_map = {}
            for rm in raw_materials_data:
                code = rm['code']
                obj, _ = RawMaterial.objects.get_or_create(code=code, defaults=rm)
                rm_map[code] = obj

            # 6. Packaging Materials
            packaging_materials_data = [
                {
                    'code': 'PM-001',
                    'name': '500ml HDPE Translucent Bottle',
                    'material_type': PackagingMaterial.MaterialType.BOTTLE,
                    'uom': uom_map['PCS'],
                    'standard_cost': Decimal('8.50'),
                    'reorder_level': Decimal('1000.00'),
                    'preferred_supplier': sup_map['SUP-003'],
                },
                {
                    'code': 'PM-002',
                    'name': '5 Litre Stackable HDPE Jerrycan',
                    'material_type': PackagingMaterial.MaterialType.BOTTLE,
                    'uom': uom_map['PCS'],
                    'standard_cost': Decimal('48.00'),
                    'reorder_level': Decimal('250.00'),
                    'preferred_supplier': sup_map['SUP-003'],
                },
                {
                    'code': 'PM-003',
                    'name': '200 Litre Industrial Epoxy-Lined Steel Drum',
                    'material_type': PackagingMaterial.MaterialType.BOTTLE,
                    'uom': uom_map['PCS'],
                    'standard_cost': Decimal('1650.00'),
                    'reorder_level': Decimal('20.00'),
                    'preferred_supplier': sup_map['SUP-003'],
                },
                {
                    'code': 'PM-004',
                    'name': 'Induction Tamper-Evident Heat Seal Cap',
                    'material_type': PackagingMaterial.MaterialType.SEAL,
                    'uom': uom_map['PCS'],
                    'standard_cost': Decimal('1.20'),
                    'reorder_level': Decimal('2000.00'),
                    'preferred_supplier': sup_map['SUP-003'],
                },
                {
                    'code': 'PM-005',
                    'name': 'Waterproof Chemical Hazard Vinyl Label',
                    'material_type': PackagingMaterial.MaterialType.LABEL,
                    'uom': uom_map['PCS'],
                    'standard_cost': Decimal('2.50'),
                    'reorder_level': Decimal('1500.00'),
                    'preferred_supplier': sup_map['SUP-003'],
                },
            ]
            pm_map = {}
            for pm in packaging_materials_data:
                code = pm['code']
                obj, _ = PackagingMaterial.objects.get_or_create(code=code, defaults=pm)
                pm_map[code] = obj

            # 7. Finished Products
            products_data = [
                {
                    'code': 'PRD-101',
                    'name': 'NIT Industrial Heavy-Duty Degreaser & Rust Remover',
                    'category': 'Industrial Chemical Solvents',
                    'base_uom': uom_map['L'],
                    'description': 'High-strength alkaline cleaner formulated for rapid removal of heavy greases, burnt hydrocarbons, and surface rust.',
                },
                {
                    'code': 'PRD-102',
                    'name': 'Precision Electro-Mechanical Contact Cleaner',
                    'category': 'Electronic Cleaners',
                    'base_uom': uom_map['L'],
                    'description': 'Residue-free fast-drying formulation designed for sensitive PCB circuitry and switchgear contacts.',
                },
                {
                    'code': 'PRD-103',
                    'name': 'High-Temperature Industrial Anti-Seize Compound',
                    'category': 'Specialty Lubricants',
                    'base_uom': uom_map['KG'],
                    'description': 'Extreme-pressure metallic anti-seize paste rated up to 1100°C for turbine bolts and kiln flanges.',
                },
            ]
            prd_map = {}
            for p in products_data:
                code = p['code']
                obj, _ = Product.objects.get_or_create(code=code, defaults=p)
                prd_map[code] = obj

            # 8. Product Pack Sizes (SKUs)
            pack_sizes_data = [
                # For PRD-101
                {
                    'product': prd_map['PRD-101'],
                    'sku_code': 'SKU-PRD101-500ML',
                    'pack_name': '500ml Retail Trigger Bottle',
                    'pack_size_value': Decimal('0.50'),
                    'uom': uom_map['L'],
                    'primary_packaging': pm_map['PM-001'],
                    'mrp': Decimal('240.00'),
                    'retailer_price': Decimal('180.00'),
                    'distributor_price': Decimal('150.00'),
                    'barcode': '8901234500018',
                },
                {
                    'product': prd_map['PRD-101'],
                    'sku_code': 'SKU-PRD101-5L',
                    'pack_name': '5 Litre Workshop Jerrycan',
                    'pack_size_value': Decimal('5.00'),
                    'uom': uom_map['L'],
                    'primary_packaging': pm_map['PM-002'],
                    'mrp': Decimal('1850.00'),
                    'retailer_price': Decimal('1420.00'),
                    'distributor_price': Decimal('1200.00'),
                    'barcode': '8901234500025',
                },
                {
                    'product': prd_map['PRD-101'],
                    'sku_code': 'SKU-PRD101-200L',
                    'pack_name': '200 Litre Plant Drum',
                    'pack_size_value': Decimal('200.00'),
                    'uom': uom_map['L'],
                    'primary_packaging': pm_map['PM-003'],
                    'mrp': Decimal('54000.00'),
                    'retailer_price': Decimal('45000.00'),
                    'distributor_price': Decimal('39500.00'),
                    'barcode': '8901234500032',
                },
                # For PRD-102
                {
                    'product': prd_map['PRD-102'],
                    'sku_code': 'SKU-PRD102-500ML',
                    'pack_name': '500ml Precision Spray Container',
                    'pack_size_value': Decimal('0.50'),
                    'uom': uom_map['L'],
                    'primary_packaging': pm_map['PM-001'],
                    'mrp': Decimal('320.00'),
                    'retailer_price': Decimal('250.00'),
                    'distributor_price': Decimal('210.00'),
                    'barcode': '8901234500049',
                },
            ]
            for ps in pack_sizes_data:
                ProductPackSize.objects.get_or_create(sku_code=ps['sku_code'], defaults=ps)

            # 9. Bill of Materials (BOM) with multiple ingredients & expected yield
            bom_prd101, _ = BillOfMaterials.objects.get_or_create(
                bom_code='BOM-PRD101-V1',
                defaults={
                    'product': prd_map['PRD-101'],
                    'name': 'Standard 1000L Industrial Degreaser Formulation',
                    'version': 'v1.0',
                    'batch_size': Decimal('1000.00'),
                    'output_uom': uom_map['L'],
                    'expected_yield_pct': Decimal('98.50'),
                    'is_active_version': True,
                    'notes': '1. Charge 500L Demineralized water into reactor.\n'
                             '2. Turn on high-shear agitator at 120 RPM.\n'
                             '3. Slowly add SLES surfactant until fully dissolved.\n'
                             '4. Dosing Phosphoric Acid and Corrosion Inhibitor sequentially.\n'
                             '5. Top up with remaining water and mix for 45 minutes.',
                }
            )

            # BOM Ingredients (both raw material and packaging lines)
            bom_items_data = [
                {
                    'bom': bom_prd101,
                    'item_type': BOMItem.ItemType.RAW_MATERIAL,
                    'raw_material': rm_map['RM-001'],
                    'quantity': Decimal('120.0000'),
                    'uom': uom_map['KG'],
                    'scrap_tolerance_pct': Decimal('0.50'),
                    'notes': 'Primary surfactant active',
                },
                {
                    'bom': bom_prd101,
                    'item_type': BOMItem.ItemType.RAW_MATERIAL,
                    'raw_material': rm_map['RM-002'],
                    'quantity': Decimal('150.0000'),
                    'uom': uom_map['L'],
                    'scrap_tolerance_pct': Decimal('1.00'),
                    'notes': 'Solvent carrier & degreasing enhancer',
                },
                {
                    'bom': bom_prd101,
                    'item_type': BOMItem.ItemType.RAW_MATERIAL,
                    'raw_material': rm_map['RM-003'],
                    'quantity': Decimal('80.0000'),
                    'uom': uom_map['KG'],
                    'scrap_tolerance_pct': Decimal('0.20'),
                    'notes': 'Deoxidizing chemical agent',
                },
                {
                    'bom': bom_prd101,
                    'item_type': BOMItem.ItemType.RAW_MATERIAL,
                    'raw_material': rm_map['RM-004'],
                    'quantity': Decimal('680.0000'),
                    'uom': uom_map['L'],
                    'scrap_tolerance_pct': Decimal('0.00'),
                    'notes': 'Balance carrier diluent',
                },
                {
                    'bom': bom_prd101,
                    'item_type': BOMItem.ItemType.RAW_MATERIAL,
                    'raw_material': rm_map['RM-005'],
                    'quantity': Decimal('15.0000'),
                    'uom': uom_map['KG'],
                    'scrap_tolerance_pct': Decimal('0.10'),
                    'notes': 'Anti-flash rust passivation agent',
                },
            ]

            for bi in bom_items_data:
                BOMItem.objects.get_or_create(
                    bom=bi['bom'],
                    raw_material=bi.get('raw_material'),
                    defaults=bi
                )

            # 10. NIT Trichy Problem Statement Benchmark: South Indian Snacks Master Data
            sup_snk, _ = Supplier.objects.get_or_create(
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

            # Raw Materials: Flour @ Rs 42/kg, Oil @ Rs 140/L, Spice mix @ Rs 200/kg
            rm_flour, _ = RawMaterial.objects.update_or_create(
                code='RM-FLOUR',
                defaults={
                    'name': 'Flour',
                    'category': 'Flours & Grains',
                    'uom': uom_map['KG'],
                    'standard_cost': Decimal('42.00'),
                    'reorder_level': Decimal('50.00'),
                    'preferred_supplier': sup_snk,
                    'description': 'High-grade rice and pulse flour for traditional South Indian Murukku preparation.',
                }
            )
            rm_oil, _ = RawMaterial.objects.update_or_create(
                code='RM-OIL',
                defaults={
                    'name': 'Oil',
                    'category': 'Edible Cooking Oils',
                    'uom': uom_map['L'],
                    'standard_cost': Decimal('140.00'),
                    'reorder_level': Decimal('20.00'),
                    'preferred_supplier': sup_snk,
                    'description': 'Refined edible frying oil for deep frying savories.',
                }
            )
            rm_spice, _ = RawMaterial.objects.update_or_create(
                code='RM-SPICE',
                defaults={
                    'name': 'Spice mix',
                    'category': 'Spices & Seasonings',
                    'uom': uom_map['KG'],
                    'standard_cost': Decimal('200.00'),
                    'reorder_level': Decimal('2.00'),
                    'preferred_supplier': sup_snk,
                    'description': 'Authentic savory spice blend (chilli, asafoetida, sesame, and salt).',
                }
            )

            # Packaging Materials: Pouches @ Rs 2.50 ea, Cartons @ Rs 15 ea (20 pkts/carton)
            pm_pouch, _ = PackagingMaterial.objects.update_or_create(
                code='PM-POUCH',
                defaults={
                    'name': 'Pouches',
                    'material_type': PackagingMaterial.MaterialType.OTHER,
                    'uom': uom_map['PCS'],
                    'standard_cost': Decimal('2.50'),
                    'reorder_level': Decimal('200.00'),
                    'preferred_supplier': sup_snk,
                }
            )
            pm_carton, _ = PackagingMaterial.objects.update_or_create(
                code='PM-CARTON',
                defaults={
                    'name': 'Cartons (20 packets/carton)',
                    'material_type': PackagingMaterial.MaterialType.CARTON,
                    'uom': uom_map['PCS'],
                    'standard_cost': Decimal('15.00'),
                    'reorder_level': Decimal('10.00'),
                    'preferred_supplier': sup_snk,
                }
            )

            # Finished Product: Murukku 200g, Selling price Rs 50 before 5% GST
            prd_murukku, _ = Product.objects.update_or_create(
                code='PRD-MURUKKU',
                defaults={
                    'name': 'Finished Murukku 200g',
                    'category': 'Traditional Savories',
                    'base_uom': uom_map['PCS'],
                    'description': 'Authentic crispy South Indian Murukku 200g packets.',
                }
            )
            ProductPackSize.objects.update_or_create(
                sku_code='SKU-MRK-200G',
                defaults={
                    'product': prd_murukku,
                    'pack_name': 'Murukku 200g Packet',
                    'pack_size_value': Decimal('0.20'),
                    'uom': uom_map['KG'],
                    'primary_packaging': pm_pouch,
                    'mrp': Decimal('52.50'),
                    'retailer_price': Decimal('50.00'),
                    'distributor_price': Decimal('50.00'),
                    'barcode': '890600100101',
                }
            )

            # Exact Benchmark BOM: Flour 40 kg, Oil 10 L, Spice 1.2 kg, Pouches 200, Cartons 10. Expected output: 200 packets.
            bom_murukku, _ = BillOfMaterials.objects.update_or_create(
                bom_code='BOM-MRK-200PKT',
                defaults={
                    'product': prd_murukku,
                    'name': 'Standard Murukku 200 Packets Benchmark Formulation',
                    'version': 'v1.0',
                    'batch_size': Decimal('200.00'),
                    'output_uom': uom_map['PCS'],
                    'expected_yield_pct': Decimal('100.00'),
                    'is_active_version': True,
                    'notes': 'Flour 40 kg, Oil 10 L, Spice 1.2 kg, Pouches 200, Cartons 10. Expected output: 200 packets.',
                }
            )

            benchmark_bom_items = [
                (BOMItem.ItemType.RAW_MATERIAL, rm_flour, None, Decimal('40.0000'), uom_map['KG'], 'Flour base dough'),
                (BOMItem.ItemType.RAW_MATERIAL, rm_oil, None, Decimal('10.0000'), uom_map['L'], 'Deep frying oil'),
                (BOMItem.ItemType.RAW_MATERIAL, rm_spice, None, Decimal('1.2000'), uom_map['KG'], 'Spice blend'),
                (BOMItem.ItemType.PACKAGING_MATERIAL, None, pm_pouch, Decimal('200.0000'), uom_map['PCS'], 'Primary pouches'),
                (BOMItem.ItemType.PACKAGING_MATERIAL, None, pm_carton, Decimal('10.0000'), uom_map['PCS'], 'Outer cartons (20 pkts/ctn)'),
            ]
            for itype, rmat, pmat, qty, uom_obj, note in benchmark_bom_items:
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

        self.stdout.write(self.style.SUCCESS("Master Data successfully seeded!"))
