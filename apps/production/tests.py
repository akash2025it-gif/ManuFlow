from decimal import Decimal
from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from django.core.management import call_command
from django.core.exceptions import ValidationError

from apps.accounts.models import CustomUser
from apps.master_data.models import (
    BillOfMaterials,
    ProductPackSize,
    RawMaterial,
    PackagingMaterial,
    UnitOfMeasurement,
)
from apps.inventory.models import StockItem, StockLedgerEntry, MovementType
from apps.production.models import ProductionRun, ProductionMaterialConsumption
from apps.production.services import (
    create_production_run_from_bom,
    post_production_run,
    get_weighted_average_cost,
)


class ExactNITProductionBenchmarkTests(TestCase):
    """
    Direct verification of the EXACT NIT Trichy Problem Statement Production Benchmark:
    - Flour issued: 40 kg
    - Oil issued: 10.5 L
    - Spice issued: 1.2 kg
    - Actual output: 188 good packets
    - Damaged pouches: 6
    - Cartons used: 9
    - Labour: Rs 1,200
    - Gas/power: Rs 600
    - Expected output: 200 packets
    - Expected flour closing: 120 kg
    - Expected oil closing: 19.5 L
    - Expected finished stock: 238 packets
    - Yield variance: -6%
    - Oil variance: +5%
    - Configurable 3% variance alert triggered on Yield (-6%) and Oil (+5%)
    - Weighted-average material costing and overhead absorption
    - Duplicate-posting protection.
    """

    def setUp(self):
        call_command('seed_snacks_benchmark')

        self.prod_user = CustomUser.objects.create_user(
            email='prod_mgr@nit.edu', username='prod_bench_user', password='Pass12345!',
            role=CustomUser.Role.PRODUCTION
        )
        self.bom = BillOfMaterials.objects.get(bom_code='BOM-MRK-200PKT')
        self.sku = ProductPackSize.objects.get(sku_code='SKU-MRK-200G')

    def test_automatic_planned_material_calculation_from_bom(self):
        # 1. Planned batch of 200 packets (1x batch scale)
        run200 = create_production_run_from_bom(
            bom=self.bom,
            planned_quantity=Decimal('200.00'),
            user=self.prod_user,
            product_pack_size=self.sku
        )
        self.assertEqual(run200.planned_quantity, Decimal('200.00'))
        self.assertEqual(run200.expected_output_quantity, Decimal('200.00'))

        mats200 = {m.item_code: m.planned_quantity for m in run200.materials.all()}
        self.assertEqual(mats200['RM-FLOUR'], Decimal('40.0000'))
        self.assertEqual(mats200['RM-OIL'], Decimal('10.0000'))
        self.assertEqual(mats200['RM-SPICE'], Decimal('1.2000'))
        self.assertEqual(mats200['PM-POUCH'], Decimal('200.0000'))
        self.assertEqual(mats200['PM-CARTON'], Decimal('10.0000'))

        # 2. Planned batch of 400 packets (2x batch scale)
        run400 = create_production_run_from_bom(
            bom=self.bom,
            planned_quantity=Decimal('400.00'),
            user=self.prod_user,
            product_pack_size=self.sku
        )
        self.assertEqual(run400.planned_quantity, Decimal('400.00'))
        self.assertEqual(run400.expected_output_quantity, Decimal('400.00'))

        mats400 = {m.item_code: m.planned_quantity for m in run400.materials.all()}
        self.assertEqual(mats400['RM-FLOUR'], Decimal('80.0000'))
        self.assertEqual(mats400['RM-OIL'], Decimal('20.0000'))
        self.assertEqual(mats400['RM-SPICE'], Decimal('2.4000'))
        self.assertEqual(mats400['PM-POUCH'], Decimal('400.0000'))
        self.assertEqual(mats400['PM-CARTON'], Decimal('20.0000'))

    def test_exact_benchmark_execution_and_variance_alerts(self):
        # Create run for 200 packets
        run = create_production_run_from_bom(
            bom=self.bom,
            planned_quantity=Decimal('200.00'),
            user=self.prod_user,
            product_pack_size=self.sku,
            batch_number='LOT-FG-MRK200-TEST01',
            variance_alert_threshold_pct=Decimal('3.00')
        )

        # Baseline check before run:
        # Flour = 160 kg (100 op @ 42 + 60 pur @ 45)
        # Oil = 30 L
        # Murukku finished goods = 50 packets
        flour_init = sum(s.quantity_on_hand for s in StockItem.objects.filter(raw_material__code='RM-FLOUR'))
        oil_init = sum(s.quantity_on_hand for s in StockItem.objects.filter(raw_material__code='RM-OIL'))
        fg_init = sum(s.quantity_on_hand for s in StockItem.objects.filter(product_pack_size=self.sku))
        self.assertEqual(flour_init, Decimal('160.0000'))
        self.assertEqual(oil_init, Decimal('30.0000'))
        self.assertEqual(fg_init, Decimal('50.0000'))

        # Set Benchmark inputs
        run.actual_output_quantity = Decimal('188.00')
        run.labour_cost = Decimal('1200.00')
        run.power_gas_cost = Decimal('600.00')
        run.save()

        # Update material lines:
        # Flour: 40 kg
        # Oil: 10.5 L (+5% variance)
        # Spice: 1.2 kg
        # Pouches: 194 (188 good + 6 damaged)
        # Cartons: 9
        for mat in run.materials.all():
            if mat.raw_material and mat.raw_material.code == 'RM-FLOUR':
                mat.actual_quantity = Decimal('40.0000')
                mat.source_batch_number = 'LOT-FLOUR-OP-01'
            elif mat.raw_material and mat.raw_material.code == 'RM-OIL':
                mat.actual_quantity = Decimal('10.5000')
                mat.source_batch_number = 'LOT-OIL-OP-01'
            elif mat.raw_material and mat.raw_material.code == 'RM-SPICE':
                mat.actual_quantity = Decimal('1.2000')
                mat.source_batch_number = 'LOT-SPICE-OP-01'
            elif mat.packaging_material and mat.packaging_material.code == 'PM-POUCH':
                mat.actual_quantity = Decimal('194.0000')
                mat.damaged_quantity = Decimal('6.0000')
                mat.source_batch_number = 'LOT-POUCH-OP-01'
            elif mat.packaging_material and mat.packaging_material.code == 'PM-CARTON':
                mat.actual_quantity = Decimal('9.0000')
                mat.source_batch_number = 'LOT-CARTON-OP-01'
            mat.save()

        # Post to inventory stock ledger
        post_production_run(run.pk, self.prod_user)
        run.refresh_from_db()

        # 1. Output Yield Verification
        self.assertEqual(run.expected_output_quantity, Decimal('200.00'))
        self.assertEqual(run.actual_output_quantity, Decimal('188.00'))
        self.assertEqual(run.yield_variance_quantity, Decimal('-12.00'))
        self.assertEqual(run.yield_variance_pct, Decimal('-6.00'))  # Exactly -6%
        self.assertTrue(run.is_yield_alert_triggered)  # |-6%| > 3% threshold

        # 2. Oil Variance Verification
        oil_mat = run.materials.get(raw_material__code='RM-OIL')
        self.assertEqual(oil_mat.planned_quantity, Decimal('10.0000'))
        self.assertEqual(oil_mat.actual_quantity, Decimal('10.5000'))
        self.assertEqual(oil_mat.variance_quantity, Decimal('0.5000'))
        self.assertEqual(oil_mat.variance_pct, Decimal('5.00'))  # Exactly +5%
        self.assertTrue(oil_mat.is_variance_alert_triggered)  # 5% > 3% threshold

        # 3. Closing Inventory Balances Verification
        flour_closing = sum(s.quantity_on_hand for s in StockItem.objects.filter(raw_material__code='RM-FLOUR'))
        oil_closing = sum(s.quantity_on_hand for s in StockItem.objects.filter(raw_material__code='RM-OIL'))
        spice_closing = sum(s.quantity_on_hand for s in StockItem.objects.filter(raw_material__code='RM-SPICE'))
        pouches_closing = sum(s.quantity_on_hand for s in StockItem.objects.filter(packaging_material__code='PM-POUCH'))
        cartons_closing = sum(s.quantity_on_hand for s in StockItem.objects.filter(packaging_material__code='PM-CARTON'))
        fg_closing = sum(s.quantity_on_hand for s in StockItem.objects.filter(product_pack_size=self.sku))

        # Assert exact expected closing stocks
        self.assertEqual(flour_closing, Decimal('120.0000'))  # Expected flour closing: 120 kg
        self.assertEqual(oil_closing, Decimal('19.5000'))      # Expected oil closing: 19.5 L
        self.assertEqual(spice_closing, Decimal('3.8000'))
        self.assertEqual(pouches_closing, Decimal('306.0000'))
        self.assertEqual(cartons_closing, Decimal('21.0000'))
        self.assertEqual(fg_closing, Decimal('238.0000'))      # Expected finished stock: 238 packets (50 + 188)

        # 4. Production Costing & Weighted-Average Material Valuation
        # Flour: 40 kg * 43.125 = 1,725.00
        # Oil: 10.5 L * 140 = 1,470.00
        # Spice: 1.2 kg * 200 = 240.00
        # Pouches: 194 * 2.50 = 485.00
        # Cartons: 9 * 15 = 135.00
        # Total Material = 4,055.00
        # Total Overheads = 1,200 + 600 = 1,800.00
        # Total Production Cost = 4,055 + 1,800 = 5,855.00
        self.assertEqual(run.total_material_cost, Decimal('4055.00'))
        self.assertEqual(run.total_overhead_cost, Decimal('1800.00'))
        self.assertEqual(run.total_production_cost, Decimal('5855.00'))
        # Unit cost = 5855 / 188 = 31.1436
        self.assertEqual(run.unit_cost_per_output, (Decimal('5855.00') / Decimal('188.00')).quantize(Decimal('0.0001')))

        # 5. Duplicate-Posting Protection
        self.assertTrue(run.is_posted)
        self.assertEqual(run.status, ProductionRun.Status.COMPLETED)
        with self.assertRaises(ValidationError):
            post_production_run(run.pk, self.prod_user)

        # 6. Verify Stock Ledger Entries
        entries = StockLedgerEntry.objects.filter(reference_type='PRODUCTION_RUN', reference_id=run.run_number)
        # 5 consumption deductions + 1 finished goods addition = 6 entries
        self.assertEqual(entries.count(), 6)

        fg_entry = entries.get(movement_type=MovementType.PRODUCTION_RECEIPT)
        self.assertEqual(fg_entry.quantity_change, Decimal('188.0000'))
        self.assertEqual(fg_entry.product_pack_size, self.sku)


class ProductionRolePermissionsAndViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = 'UniversalPass123!'

        call_command('seed_snacks_benchmark')
        self.bom = BillOfMaterials.objects.get(bom_code='BOM-MRK-200PKT')
        self.sku = ProductPackSize.objects.get(sku_code='SKU-MRK-200G')

        self.admin = CustomUser.objects.create_user(
            email='admin_perm@nit.edu', username='admin_prod', password=self.password,
            role=CustomUser.Role.ADMIN, is_staff=True
        )
        self.prod_user = CustomUser.objects.create_user(
            email='prod_perm@nit.edu', username='prod_worker', password=self.password,
            role=CustomUser.Role.PRODUCTION
        )
        self.salesman = CustomUser.objects.create_user(
            email='sales_perm@nit.edu', username='sales_visitor', password=self.password,
            role=CustomUser.Role.SALESMAN
        )
        self.auditor = CustomUser.objects.create_user(
            email='audit_perm@nit.edu', username='auditor_viewer', password=self.password,
            role=CustomUser.Role.AUDITOR
        )
        self.owner = CustomUser.objects.create_user(
            email='owner_perm@nit.edu', username='owner_exec', password=self.password,
            role=CustomUser.Role.OWNER
        )

        # Create a sample run
        self.run = create_production_run_from_bom(
            bom=self.bom,
            planned_quantity=Decimal('200.00'),
            user=self.prod_user,
            product_pack_size=self.sku
        )

    def test_production_hub_access(self):
        # Unauthenticated -> redirect to login
        res = self.client.get(reverse('production_hub'))
        self.assertEqual(res.status_code, 302)

        # Authenticated production user -> 200 OK
        self.client.login(username='prod_worker', password=self.password)
        res = self.client.get(reverse('production_hub'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Production Control & Yield Observatory")

    def test_salesman_cannot_create_or_execute_runs(self):
        self.client.login(username='sales_visitor', password=self.password)

        # Salesman GET on run_create -> 403 Forbidden
        res = self.client.get(reverse('production_run_create'))
        self.assertEqual(res.status_code, 403)

        # Salesman GET on run_execute -> 403 Forbidden
        res = self.client.get(reverse('production_run_execute', kwargs={'pk': self.run.pk}))
        self.assertEqual(res.status_code, 403)

    def test_auditor_and_owner_read_only_access(self):
        # Auditor can view work order detail and reports
        self.client.login(username='auditor_viewer', password=self.password)

        res = self.client.get(reverse('production_run_detail', kwargs={'pk': self.run.pk}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, self.run.run_number)

        res = self.client.get(reverse('production_reports'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Production History & Variance Intelligence")

        # Auditor cannot post run -> 403 Forbidden
        res = self.client.post(reverse('production_run_post', kwargs={'pk': self.run.pk}))
        self.assertEqual(res.status_code, 403)

        # Owner can view reports
        self.client.login(username='owner_exec', password=self.password)
        res = self.client.get(reverse('production_reports'))
        self.assertEqual(res.status_code, 200)

    def test_production_user_can_create_and_execute_run(self):
        self.client.login(username='prod_worker', password=self.password)

        res = self.client.post(reverse('production_run_create'), {
            'bill_of_materials': self.bom.pk,
            'product_pack_size': self.sku.pk,
            'planned_quantity': '200.00',
            'batch_number': 'LOT-TEST-NEW',
            'manufacture_date': date.today().strftime('%Y-%m-%d'),
            'variance_alert_threshold_pct': '3.00',
            'notes': 'Test run creation',
        })
        self.assertEqual(res.status_code, 302)
        new_run = ProductionRun.objects.get(batch_number='LOT-TEST-NEW')
        self.assertEqual(new_run.planned_quantity, Decimal('200.00'))
        self.assertEqual(new_run.materials.count(), 5)
