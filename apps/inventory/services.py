from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import F

from .models import (
    ItemType,
    MovementType,
    StockItem,
    StockLedgerEntry,
    GoodsReceiptNote,
    StockAdjustment,
)
from apps.core.models import AuditLogEntry
from apps.core.audit import log_audit_event


def generate_transaction_number():
    """Generates a unique timestamp-based stock transaction ID."""
    now = timezone.now()
    timestamp_str = now.strftime('%Y%m%d%H%M%S%f')
    return f"TXN-{timestamp_str[:17]}"


@transaction.atomic
def record_stock_movement(
    item_type,
    movement_type,
    quantity_change,
    uom,
    unit_cost,
    reference_type,
    reference_id,
    performed_by,
    raw_material=None,
    packaging_material=None,
    product_pack_size=None,
    batch_number='',
    expiry_date=None,
    location='Central Warehouse',
    remarks=''
):
    """
    Core atomic ledger service.
    Guarantees:
    1. Select for update on StockItem record to prevent race conditions.
    2. Zero negative stock: opening + quantity_change >= 0.
    3. Ledger invariant: opening + receipts - issues = closing.
    4. Automatically updates real-time stock balance cache.
    """
    quantity_change = Decimal(str(quantity_change))
    unit_cost = Decimal(str(unit_cost)).quantize(Decimal('0.01'))
    batch_number = (batch_number or '').strip().upper()

    # Query or create StockItem with row-level lock
    stock_item, created = StockItem.objects.select_for_update().get_or_create(
        item_type=item_type,
        raw_material=raw_material,
        packaging_material=packaging_material,
        product_pack_size=product_pack_size,
        batch_number=batch_number,
        location=location,
        defaults={
            'quantity_on_hand': Decimal('0.0000'),
            'uom': uom,
            'unit_cost': unit_cost,
            'expiry_date': expiry_date,
        }
    )

    opening_quantity = stock_item.quantity_on_hand
    closing_quantity = opening_quantity + quantity_change

    # Prevent negative stock
    if closing_quantity < Decimal('0.0000'):
        raise ValidationError(
            f"Negative inventory prohibited! Current stock of {stock_item.item_name} "
            f"is {opening_quantity} {uom.code}. Attempted movement of {quantity_change} {uom.code} "
            f"would cause negative closing balance ({closing_quantity} {uom.code})."
        )

    total_value = (abs(quantity_change) * unit_cost).quantize(Decimal('0.01'))

    # Create immutable ledger entry
    entry = StockLedgerEntry(
        entry_number=generate_transaction_number(),
        movement_type=movement_type,
        item_type=item_type,
        raw_material=raw_material,
        packaging_material=packaging_material,
        product_pack_size=product_pack_size,
        batch_number=batch_number,
        expiry_date=expiry_date or stock_item.expiry_date,
        uom=uom,
        opening_quantity=opening_quantity,
        quantity_change=quantity_change,
        closing_quantity=closing_quantity,
        unit_cost=unit_cost,
        total_value=total_value,
        reference_type=reference_type,
        reference_id=reference_id,
        performed_by=performed_by,
        remarks=remarks,
    )
    entry.full_clean()
    entry.save()

    # Update current stock snapshot
    stock_item.quantity_on_hand = closing_quantity
    if unit_cost > Decimal('0.00'):
        stock_item.unit_cost = unit_cost
    if expiry_date and not stock_item.expiry_date:
        stock_item.expiry_date = expiry_date
    stock_item.save(update_fields=['quantity_on_hand', 'unit_cost', 'expiry_date', 'last_updated'])

    return entry


@transaction.atomic
def post_goods_receipt(grn_id, user):
    """
    Verifies and posts a Goods Receipt Note to inventory.
    Prevents duplicate posting via atomic lock and status checks.
    """
    grn = GoodsReceiptNote.objects.select_for_update().get(pk=grn_id)

    if grn.is_posted:
        raise ValidationError("This Goods Receipt Note has already been posted to inventory.")

    if grn.status == GoodsReceiptNote.Status.CANCELLED:
        raise ValidationError("Cancelled GRNs cannot be posted to inventory.")

    for item in grn.items.all():
        if item.accepted_quantity > Decimal('0.0000'):
            record_stock_movement(
                item_type=item.item_type,
                movement_type=MovementType.PURCHASE_RECEIPT,
                quantity_change=item.accepted_quantity,
                uom=item.uom,
                unit_cost=item.unit_price,
                reference_type='GRN',
                reference_id=grn.grn_number,
                performed_by=user,
                raw_material=item.raw_material,
                packaging_material=item.packaging_material,
                batch_number=item.batch_number,
                expiry_date=item.expiry_date,
                location=item.storage_location,
                remarks=f"Inbound receipt via {grn.grn_number} from {grn.supplier.name} (Challan: {grn.supplier_invoice_no})"
            )

            # Update PO line received quantity if linked
            if item.po_item:
                po_item = item.po_item
                po_item.received_quantity = F('received_quantity') + item.accepted_quantity
                po_item.save(update_fields=['received_quantity'])

    # Update PO status if linked
    if grn.purchase_order:
        po = grn.purchase_order
        po.refresh_from_db()
        po.update_totals()

    grn.is_posted = True
    grn.status = GoodsReceiptNote.Status.POSTED
    grn.posted_at = timezone.now()
    grn.save(update_fields=['is_posted', 'status', 'posted_at'])

    log_audit_event(
        action=AuditLogEntry.Action.GRN_POSTED,
        module=AuditLogEntry.Module.INVENTORY,
        object_repr=f"GRN {grn.grn_number} from {grn.supplier.name}",
        object_id=str(grn.pk),
        reference_number=grn.grn_number,
        user=user,
        details={
            'supplier': grn.supplier.name,
            'challan_no': grn.supplier_invoice_no,
            'items_count': grn.items.count(),
            'po_number': grn.purchase_order.po_number if grn.purchase_order else None
        }
    )

    return grn


@transaction.atomic
def post_stock_adjustment(adjustment_id, user):
    """
    Applies audited physical count discrepancies to the stock ledger.
    Prevents duplicate posting.
    """
    adjustment = StockAdjustment.objects.select_for_update().get(pk=adjustment_id)

    if adjustment.is_posted:
        raise ValidationError("This Stock Adjustment has already been posted.")

    if adjustment.status == StockAdjustment.Status.CANCELLED:
        raise ValidationError("Cancelled adjustments cannot be posted.")

    for item in adjustment.items.all():
        variance = item.variance_quantity
        if variance == Decimal('0.0000'):
            continue

        movement_type = (
            MovementType.STOCK_ADJUSTMENT_IN
            if variance > Decimal('0.0000')
            else MovementType.STOCK_ADJUSTMENT_OUT
        )

        record_stock_movement(
            item_type=item.item_type,
            movement_type=movement_type,
            quantity_change=variance,
            uom=item.uom,
            unit_cost=item.unit_cost,
            reference_type='ADJUSTMENT',
            reference_id=adjustment.adjustment_number,
            performed_by=user,
            raw_material=item.raw_material,
            packaging_material=item.packaging_material,
            product_pack_size=item.product_pack_size,
            batch_number=item.batch_number,
            remarks=f"Inventory audit reconciliation ({adjustment.get_reason_display()}). {item.remarks}"
        )

    adjustment.is_posted = True
    adjustment.status = StockAdjustment.Status.POSTED
    adjustment.posted_at = timezone.now()
    adjustment.approved_by = user
    adjustment.save(update_fields=['is_posted', 'status', 'posted_at', 'approved_by'])

    log_audit_event(
        action=AuditLogEntry.Action.STOCK_ADJUSTMENT,
        module=AuditLogEntry.Module.INVENTORY,
        object_repr=f"Stock Adjustment {adjustment.adjustment_number}",
        object_id=str(adjustment.pk),
        reference_number=adjustment.adjustment_number,
        user=user,
        details={
            'reason': adjustment.reason,
            'items_count': adjustment.items.count()
        }
    )

    return adjustment
