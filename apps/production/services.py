from decimal import Decimal
from datetime import date, timedelta
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.master_data.models import (
    Product,
    ProductPackSize,
    BillOfMaterials,
    BOMItem,
    RawMaterial,
    PackagingMaterial,
)
from apps.inventory.models import (
    ItemType,
    MovementType,
    StockItem,
    StockLedgerEntry,
)
from apps.inventory.services import record_stock_movement
from apps.core.models import AuditLogEntry
from apps.core.audit import log_audit_event
from .models import ProductionRun, ProductionMaterialConsumption


def generate_production_run_number():
    """Generates a unique chronological Production Run Work Order number."""
    now = timezone.now()
    timestamp_str = now.strftime('%Y%m%d%H%M%S%f')
    return f"PRUN-{timestamp_str[:17]}"


def get_weighted_average_cost(raw_material=None, packaging_material=None):
    """
    Computes the effective weighted-average inventory unit cost across all current stock on hand:
    Weighted Avg Cost = Total Valuation on Hand / Total Quantity on Hand.
    If no stock is currently on hand, falls back to the configured standard procurement cost.
    """
    qs = StockItem.objects.filter(quantity_on_hand__gt=0)
    if raw_material:
        qs = qs.filter(raw_material=raw_material)
        fallback_cost = raw_material.standard_cost
    elif packaging_material:
        qs = qs.filter(packaging_material=packaging_material)
        fallback_cost = packaging_material.standard_cost
    else:
        return Decimal('0.0000')

    total_qty = sum(item.quantity_on_hand for item in qs)
    if total_qty > Decimal('0.0000'):
        total_val = sum(item.quantity_on_hand * item.unit_cost for item in qs)
        return (total_val / total_qty).quantize(Decimal('0.0001'))
    return fallback_cost.quantize(Decimal('0.0001'))


@transaction.atomic
def create_production_run_from_bom(
    bom,
    planned_quantity,
    user,
    product_pack_size=None,
    batch_number='',
    manufacture_date=None,
    expiry_date=None,
    variance_alert_threshold_pct=Decimal('3.00'),
    notes=''
):
    """
    Creates a new ProductionRun and automatically calculates planned ingredient
    and packaging requirements from the linked Bill of Materials (BOM).
    """
    planned_quantity = Decimal(str(planned_quantity))
    if planned_quantity <= Decimal('0.00'):
        raise ValidationError("Planned batch quantity must be strictly greater than 0.")

    # Determine pack size SKU if not supplied
    if not product_pack_size:
        product_pack_size = bom.product.pack_sizes.filter(is_active=True).first()
        if not product_pack_size:
            raise ValidationError(f"Product {bom.product.name} has no commercial Pack Size SKUs configured.")

    # Calculate scale factor relative to standard BOM batch size
    scale_factor = planned_quantity / bom.batch_size
    expected_output = (planned_quantity * (bom.expected_yield_pct / Decimal('100.00'))).quantize(Decimal('0.01'))

    # Generate identifiers if not provided
    run_num = generate_production_run_number()
    mfd = manufacture_date or date.today()
    if not batch_number:
        batch_number = f"LOT-FG-{product_pack_size.sku_code[:6]}-{mfd.strftime('%y%m%d')}"
    if not expiry_date:
        expiry_date = mfd + timedelta(days=90)

    # Instantiate and save ProductionRun
    run = ProductionRun.objects.create(
        run_number=run_num,
        bill_of_materials=bom,
        product=bom.product,
        product_pack_size=product_pack_size,
        planned_quantity=planned_quantity,
        expected_output_quantity=expected_output,
        actual_output_quantity=Decimal('0.00'),
        damaged_quantity=Decimal('0.00'),
        batch_number=batch_number,
        manufacture_date=mfd,
        expiry_date=expiry_date,
        status=ProductionRun.Status.DRAFT,
        variance_alert_threshold_pct=variance_alert_threshold_pct,
        created_by=user,
        notes=notes
    )

    # Populate planned material consumption lines from BOM constituents
    for bom_item in bom.items.all():
        req_qty = (bom_item.quantity * scale_factor).quantize(Decimal('0.0001'))
        current_wac = get_weighted_average_cost(
            raw_material=bom_item.raw_material,
            packaging_material=bom_item.packaging_material
        )
        line_cost = (req_qty * current_wac).quantize(Decimal('0.01'))

        # Set default source batch from existing stock on hand if available
        src_batch = ''
        if bom_item.raw_material:
            stk = StockItem.objects.filter(raw_material=bom_item.raw_material, quantity_on_hand__gt=0).first()
            if stk:
                src_batch = stk.batch_number
        elif bom_item.packaging_material:
            stk = StockItem.objects.filter(packaging_material=bom_item.packaging_material, quantity_on_hand__gt=0).first()
            if stk:
                src_batch = stk.batch_number

        ProductionMaterialConsumption.objects.create(
            production_run=run,
            item_type=bom_item.item_type,
            raw_material=bom_item.raw_material,
            packaging_material=bom_item.packaging_material,
            uom=bom_item.uom,
            planned_quantity=req_qty,
            actual_quantity=req_qty,  # default actual to planned
            damaged_quantity=Decimal('0.0000'),
            unit_cost=current_wac,
            total_cost=line_cost,
            source_batch_number=src_batch,
            notes=bom_item.notes
        )

    log_audit_event(
        action=AuditLogEntry.Action.PRODUCTION_CREATE,
        module=AuditLogEntry.Module.PRODUCTION,
        object_repr=f"Production Run {run.run_number}",
        object_id=str(run.pk),
        reference_number=run.run_number,
        user=user,
        details={
            'bom_code': bom.bom_code,
            'product': bom.product.name,
            'planned_quantity': run.planned_quantity,
            'expected_output': run.expected_output_quantity,
            'batch_number': run.batch_number
        }
    )

    return run


@transaction.atomic
def post_production_run(run_id, user):
    """
    Executes atomic completion and inventory posting for a Production Run:
    1. Enforces duplicate-posting protection.
    2. Recalculates weighted-average costs for actual consumption.
    3. Deducts consumed raw materials & packaging from inventory stock via StockLedgerEntry.
    4. Computes total batch cost (Materials + Labour + Gas/Power Overheads) and finished unit cost.
    5. Adds finished goods output into inventory stock via StockLedgerEntry.
    6. Marks run as COMPLETED.
    """
    run = ProductionRun.objects.select_for_update().get(pk=run_id)

    # 1. Duplicate-posting protection
    if run.is_posted:
        raise ValidationError(f"Production Run {run.run_number} has already been posted to the inventory ledger!")

    if run.actual_output_quantity <= Decimal('0.00'):
        raise ValidationError("Cannot complete production run: Actual output quantity must be greater than zero.")

    # 2. Process Material Deductions
    for item in run.materials.all():
        actual_qty = item.actual_quantity
        if actual_qty <= Decimal('0.0000'):
            continue

        # Get latest weighted average cost for valuation
        wac = get_weighted_average_cost(
            raw_material=item.raw_material,
            packaging_material=item.packaging_material
        )
        item.unit_cost = wac
        item.total_cost = (actual_qty * wac).quantize(Decimal('0.01'))
        item.save(update_fields=['unit_cost', 'total_cost'])

        # Determine which stock batch to deduct from
        # If source batch specified and has stock, use it; otherwise deduct FIFO from available batches
        qty_to_deduct = actual_qty

        if item.raw_material:
            stock_qs = StockItem.objects.filter(raw_material=item.raw_material, quantity_on_hand__gt=0).order_by('id')
        else:
            stock_qs = StockItem.objects.filter(packaging_material=item.packaging_material, quantity_on_hand__gt=0).order_by('id')

        # Prioritize specified source_batch_number if it exists
        if item.source_batch_number:
            priority_qs = stock_qs.filter(batch_number=item.source_batch_number)
            if priority_qs.exists():
                stock_qs = list(priority_qs) + list(stock_qs.exclude(batch_number=item.source_batch_number))

        total_available = sum(s.quantity_on_hand for s in stock_qs)
        if total_available < qty_to_deduct:
            raise ValidationError(
                f"Insufficient stock for {item.item_name}! Required: {qty_to_deduct} {item.uom.code}, "
                f"Available on hand: {total_available} {item.uom.code}."
            )

        for stock in stock_qs:
            if qty_to_deduct <= Decimal('0.0000'):
                break

            deduct_from_batch = min(stock.quantity_on_hand, qty_to_deduct)

            record_stock_movement(
                item_type=item.item_type,
                movement_type=MovementType.PRODUCTION_CONSUMPTION,
                quantity_change=-deduct_from_batch,
                uom=item.uom,
                unit_cost=wac,
                reference_type='PRODUCTION_RUN',
                reference_id=run.run_number,
                performed_by=user,
                raw_material=item.raw_material,
                packaging_material=item.packaging_material,
                batch_number=stock.batch_number,
                remarks=f"Production Run {run.run_number} material consumption"
            )
            qty_to_deduct -= deduct_from_batch

    # 3. Compute Finished Goods Unit Cost & Post Receipt
    unit_cost_output = run.unit_cost_per_output

    record_stock_movement(
        item_type=ItemType.FINISHED_GOODS,
        movement_type=MovementType.PRODUCTION_RECEIPT,
        quantity_change=run.actual_output_quantity,
        uom=run.product_pack_size.uom,
        unit_cost=unit_cost_output,
        reference_type='PRODUCTION_RUN',
        reference_id=run.run_number,
        performed_by=user,
        product_pack_size=run.product_pack_size,
        batch_number=run.batch_number,
        expiry_date=run.expiry_date,
        remarks=f"Production Run {run.run_number} finished goods receipt"
    )

    # 4. Finalize Run Status & Posting Flags
    run.status = ProductionRun.Status.COMPLETED
    run.is_posted = True
    run.posted_at = timezone.now()
    run.posted_by = user
    run.save(update_fields=['status', 'is_posted', 'posted_at', 'posted_by', 'updated_at'])

    log_audit_event(
        action=AuditLogEntry.Action.PRODUCTION_POST,
        module=AuditLogEntry.Module.PRODUCTION,
        object_repr=f"Production Run {run.run_number} Finished Receipt",
        object_id=str(run.pk),
        reference_number=run.run_number,
        user=user,
        details={
            'batch_number': run.batch_number,
            'planned_quantity': run.planned_quantity,
            'actual_output_quantity': run.actual_output_quantity,
            'yield_variance_pct': run.yield_variance_pct,
            'is_yield_alert_triggered': run.is_yield_alert_triggered,
            'total_production_cost': run.total_production_cost,
            'unit_cost_per_output': run.unit_cost_per_output
        }
    )

    return run
