from decimal import Decimal
from datetime import date
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.accounts.models import CustomUser
from apps.accounts.utils import get_or_create_demo_user
from apps.master_data.models import BillOfMaterials, ProductPackSize, RawMaterial, PackagingMaterial
from apps.inventory.models import StockItem, StockLedgerEntry
from apps.production.models import ProductionRun, ProductionMaterialConsumption
from apps.production.services import create_production_run_from_bom, post_production_run, get_weighted_average_cost


class Command(BaseCommand):
    help = (
        'Executes and verifies the exact NIT Trichy Production Management Benchmark:\n'
        '- Flour issued: 40 kg (Expected closing: 120 kg)\n'
        '- Oil issued: 10.5 L (Expected closing: 19.5 L, Variance: +5%)\n'
        '- Spice issued: 1.2 kg\n'
        '- Actual good output: 188 packets (Expected output: 200 packets, Yield variance: -6%)\n'
        '- Damaged pouches: 6\n'
        '- Cartons used: 9\n'
        '- Labour overhead: Rs 1,200\n'
        '- Gas/power overhead: Rs 600\n'
        '- Expected finished stock: 238 packets (Opening 50 + Produced 188)\n'
        '- 3% Configurable alert triggered on Yield (-6%) and Oil (+5%)'
    )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting NIT Trichy Production Benchmark Execution..."))

        # 1. Ensure baseline benchmark inventory is present
        call_command('seed_snacks_benchmark')

        User = get_user_model()
        user = (
            User.objects.filter(role=CustomUser.Role.PRODUCTION, is_active=True).first()
            or User.objects.filter(is_superuser=True, is_active=True).first()
            or get_or_create_demo_user(CustomUser.Role.PRODUCTION)
        )

        # 2. Retrieve Master Data
        bom = BillOfMaterials.objects.get(bom_code='BOM-MRK-200PKT')
        sku = ProductPackSize.objects.get(sku_code='SKU-MRK-200G')

        # Clean prior benchmark production run if present to ensure idempotency
        run_bench_code = 'PRUN-NIT-BENCH-001'
        prior_run = ProductionRun.objects.filter(run_number=run_bench_code).first()
        if prior_run:
            self.stdout.write("Resetting prior benchmark production run for clean execution...")
            StockLedgerEntry.objects.filter(reference_type='PRODUCTION_RUN', reference_id=run_bench_code).delete()
            prior_run.materials.all().delete()
            prior_run.delete()
            # Re-seed baseline inventory
            call_command('seed_snacks_benchmark', reset=True)

        # 3. Create Production Run from BOM
        with transaction.atomic():
            run = create_production_run_from_bom(
                bom=bom,
                planned_quantity=Decimal('200.00'),
                user=user,
                product_pack_size=sku,
                batch_number='LOT-FG-MRK200-BNCH01',
                manufacture_date=date.today(),
                variance_alert_threshold_pct=Decimal('3.00'),
                notes='NIT Trichy Order-to-Audit Benchmark Production Run'
            )
            # Assign fixed benchmark code
            run.run_number = run_bench_code
            run.save(update_fields=['run_number'])

            # 4. Set Benchmark Actual Consumptions & Measurements
            # Actual Output: 188 good packets (shortfall of 12 packets = -6.00%)
            run.actual_output_quantity = Decimal('188.00')
            run.damaged_quantity = Decimal('0.00')

            # Overheads
            run.labour_cost = Decimal('1200.00')
            run.power_gas_cost = Decimal('600.00')
            run.other_overhead_cost = Decimal('0.00')
            run.save()

            # Materials: Flour 40kg, Oil 10.5L (+5%), Spice 1.2kg, Pouches 194 (188 good + 6 damaged), Cartons 9
            for mat in run.materials.all():
                if mat.raw_material and mat.raw_material.code == 'RM-FLOUR':
                    mat.actual_quantity = Decimal('40.0000')
                    mat.source_batch_number = 'LOT-FLOUR-OP-01'
                elif mat.raw_material and mat.raw_material.code == 'RM-OIL':
                    mat.actual_quantity = Decimal('10.5000')  # +5% variance
                    mat.source_batch_number = 'LOT-OIL-OP-01'
                elif mat.raw_material and mat.raw_material.code == 'RM-SPICE':
                    mat.actual_quantity = Decimal('1.2000')
                    mat.source_batch_number = 'LOT-SPICE-OP-01'
                elif mat.packaging_material and mat.packaging_material.code == 'PM-POUCH':
                    # 188 good packets packed + 6 damaged pouches = 194 total pouches consumed
                    mat.actual_quantity = Decimal('194.0000')
                    mat.damaged_quantity = Decimal('6.0000')
                    mat.source_batch_number = 'LOT-POUCH-OP-01'
                elif mat.packaging_material and mat.packaging_material.code == 'PM-CARTON':
                    # 9 outer master cartons used
                    mat.actual_quantity = Decimal('9.0000')
                    mat.source_batch_number = 'LOT-CARTON-OP-01'
                mat.save()

            # 5. Post Run to Inventory Stock Ledger
            post_production_run(run.pk, user)

        # 6. Verify and Print Benchmark Audit Report
        self.stdout.write(self.style.SUCCESS("\n======================================================="))
        self.stdout.write(self.style.SUCCESS("    NIT TRICHY PRODUCTION BENCHMARK AUDIT REPORT"))
        self.stdout.write(self.style.SUCCESS("======================================================="))

        # Output Yield Verification
        self.stdout.write(f"Planned Output:      {run.planned_quantity} packets")
        self.stdout.write(f"Expected Output:     {run.expected_output_quantity} packets")
        self.stdout.write(f"Actual Good Output:  {run.actual_output_quantity} packets")
        self.stdout.write(f"Yield Shortfall:     {run.yield_variance_quantity} packets")
        self.stdout.write(f"Yield Variance:      {run.yield_variance_pct}% (Expected: -6.00%)")
        self.stdout.write(f"Yield 3% Alert:      {'TRIGGERED' if run.is_yield_alert_triggered else 'NORMAL'}")

        # Material Variances Verification
        self.stdout.write("\nMaterial Consumption & Variances:")
        for mat in run.materials.all():
            alert_str = " [ALERT > 3%]" if mat.is_variance_alert_triggered else ""
            self.stdout.write(
                f"  - {mat.item_name:<26}: Planned {mat.planned_quantity} {mat.uom.code} | "
                f"Actual {mat.actual_quantity} {mat.uom.code} | Variance {mat.variance_pct}%{alert_str}"
            )

        # Costing & Overheads Breakdown
        self.stdout.write("\nCosting Breakdown:")
        self.stdout.write(f"  - Total Material Cost:   Rs {run.total_material_cost}")
        self.stdout.write(f"  - Labour Overhead:       Rs {run.labour_cost}")
        self.stdout.write(f"  - Gas / Power Overhead:  Rs {run.power_gas_cost}")
        self.stdout.write(f"  - Total Overhead Cost:   Rs {run.total_overhead_cost}")
        self.stdout.write(f"  - Total Production Cost: Rs {run.total_production_cost}")
        self.stdout.write(f"  - Finished Unit Cost:    Rs {run.unit_cost_per_output} / packet")

        # Closing Inventory Balances Verification
        flour_stock = sum(s.quantity_on_hand for s in StockItem.objects.filter(raw_material__code='RM-FLOUR'))
        oil_stock = sum(s.quantity_on_hand for s in StockItem.objects.filter(raw_material__code='RM-OIL'))
        spice_stock = sum(s.quantity_on_hand for s in StockItem.objects.filter(raw_material__code='RM-SPICE'))
        pouch_stock = sum(s.quantity_on_hand for s in StockItem.objects.filter(packaging_material__code='PM-POUCH'))
        carton_stock = sum(s.quantity_on_hand for s in StockItem.objects.filter(packaging_material__code='PM-CARTON'))
        fg_stock = sum(s.quantity_on_hand for s in StockItem.objects.filter(product_pack_size__sku_code='SKU-MRK-200G'))

        self.stdout.write("\nClosing Inventory Balances:")
        self.stdout.write(f"  - Flour Closing Stock:   {flour_stock} kg (Expected: 120 kg)")
        self.stdout.write(f"  - Oil Closing Stock:     {oil_stock} L (Expected: 19.5 L)")
        self.stdout.write(f"  - Spice mix Closing:     {spice_stock} kg (Expected: 3.8 kg)")
        self.stdout.write(f"  - Pouches Closing:       {pouch_stock} pcs (Expected: 306 pcs)")
        self.stdout.write(f"  - Cartons Closing:       {carton_stock} pcs (Expected: 21 pcs)")
        self.stdout.write(f"  - Finished Murukku 200g: {fg_stock} pkts (Expected: 238 pkts = 50 opening + 188 produced)")

        # Assertions
        assert run.expected_output_quantity == Decimal('200.00'), "Expected output must be 200 packets"
        assert run.actual_output_quantity == Decimal('188.00'), "Actual output must be 188 packets"
        assert run.yield_variance_pct == Decimal('-6.00'), "Yield variance must be -6.00%"
        assert flour_stock == Decimal('120.0000'), "Flour closing must be 120 kg"
        assert oil_stock == Decimal('19.5000'), "Oil closing must be 19.5 L"
        assert fg_stock == Decimal('238.0000'), "Finished goods closing must be 238 packets"

        oil_item = run.materials.get(raw_material__code='RM-OIL')
        assert oil_item.variance_pct == Decimal('5.00'), "Oil variance must be +5.00%"
        assert oil_item.is_variance_alert_triggered, "Oil variance must trigger 3% alert"

        self.stdout.write(self.style.SUCCESS("\nAll calculations match the NIT Trichy Benchmark Problem Statement EXACTLY!"))
        self.stdout.write(self.style.SUCCESS("=======================================================\n"))
