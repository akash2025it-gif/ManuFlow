from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Sum, F, Count
from django.core.paginator import Paginator
from django.db import transaction
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from apps.core.models import AuditLogEntry
from apps.core.audit import log_audit_event
from apps.accounts.models import CustomUser
from apps.master_data.models import (
    Supplier,
    RawMaterial,
    PackagingMaterial,
    ProductPackSize,
    UnitOfMeasurement,
)
from .models import (
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
from .forms import (
    PurchaseOrderForm,
    PurchaseOrderItemFormSet,
    GoodsReceiptNoteForm,
    GoodsReceiptItemFormSet,
    StockAdjustmentForm,
    StockAdjustmentItemFormSet,
)
from .services import post_goods_receipt, post_stock_adjustment


# ==============================================================================
# Role-Based Permission Helpers
# ==============================================================================

def can_manage_inventory(user):
    """Admin, Production Manager, and Owner have write permissions in Inventory & Purchase."""
    return user.is_superuser or user.role in [
        CustomUser.Role.ADMIN,
        CustomUser.Role.PRODUCTION,
        CustomUser.Role.OWNER,
    ]


# ==============================================================================
# 1. Inventory & Purchase Dashboard
# ==============================================================================

@login_required
def inventory_dashboard_view(request):
    """
    Central operational command center for inventory valuations, low-stock warnings,
    pending procurement orders, and recent ledger transactions.
    """
    stock_items = StockItem.objects.select_related('raw_material', 'packaging_material', 'product_pack_size', 'uom').all()

    # Calculate valuations
    total_valuation = Decimal('0.00')
    rm_valuation = Decimal('0.00')
    pm_valuation = Decimal('0.00')
    fg_valuation = Decimal('0.00')

    low_stock_items = []

    for item in stock_items:
        val = item.total_valuation
        total_valuation += val
        if item.item_type == ItemType.RAW_MATERIAL:
            rm_valuation += val
            if item.is_low_stock:
                low_stock_items.append(item)
        elif item.item_type == ItemType.PACKAGING_MATERIAL:
            pm_valuation += val
            if item.is_low_stock:
                low_stock_items.append(item)
        elif item.item_type == ItemType.FINISHED_GOODS:
            fg_valuation += val

    pending_pos = PurchaseOrder.objects.filter(
        status__in=[PurchaseOrder.Status.APPROVED, PurchaseOrder.Status.PARTIALLY_RECEIVED]
    ).count()

    recent_movements = StockLedgerEntry.objects.select_related(
        'raw_material', 'packaging_material', 'product_pack_size', 'uom', 'performed_by'
    ).order_by('-timestamp')[:8]

    context = {
        'page_title': 'Inventory & Procurement Observatory',
        'metrics': {
            'total_valuation': total_valuation,
            'rm_valuation': rm_valuation,
            'pm_valuation': pm_valuation,
            'fg_valuation': fg_valuation,
            'low_stock_count': len(low_stock_items),
            'pending_pos': pending_pos,
            'total_skus': stock_items.count(),
        },
        'low_stock_items': low_stock_items[:5],
        'recent_movements': recent_movements,
        'can_manage': can_manage_inventory(request.user),
    }
    return render(request, 'inventory/dashboard.html', context)


# ==============================================================================
# 2. Purchase Orders
# ==============================================================================

@login_required
def purchase_order_list_view(request):
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()

    orders = PurchaseOrder.objects.select_related('supplier', 'created_by').prefetch_related('items')

    if query:
        orders = orders.filter(Q(po_number__icontains=query) | Q(supplier__name__icontains=query))
    if status:
        orders = orders.filter(status=status)

    paginator = Paginator(orders, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'inventory/po_list.html', {
        'page_title': 'Supplier Purchase Orders (PO)',
        'page_obj': page_obj,
        'query': query,
        'status': status,
        'status_choices': PurchaseOrder.Status.choices,
        'can_manage': can_manage_inventory(request.user),
    })


@login_required
def purchase_order_detail_view(request, pk):
    po = get_object_or_404(
        PurchaseOrder.objects.select_related('supplier', 'created_by', 'approved_by'),
        pk=pk
    )
    items = po.items.select_related('raw_material', 'packaging_material', 'uom').all()
    receipts = po.receipts.select_related('received_by').all()

    return render(request, 'inventory/po_detail.html', {
        'page_title': f"PO {po.po_number} - {po.supplier.name}",
        'po': po,
        'items': items,
        'receipts': receipts,
        'can_manage': can_manage_inventory(request.user),
    })


@login_required
def purchase_order_create_view(request):
    if not can_manage_inventory(request.user):
        raise PermissionDenied("You do not have permission to issue purchase orders.")

    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST)
        formset = PurchaseOrderItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                po = form.save(commit=False)
                po.created_by = request.user
                po.save()
                formset.instance = po
                formset.save()
                po.update_totals()

                log_audit_event(
                    action=AuditLogEntry.Action.PO_CREATED,
                    module=AuditLogEntry.Module.INVENTORY,
                    object_repr=f"Purchase Order {po.po_number}",
                    object_id=str(po.pk),
                    reference_number=po.po_number,
                    user=request.user,
                    request=request,
                    details={
                        'supplier': po.supplier.name,
                        'total_amount': po.total_amount,
                        'status': po.status
                    }
                )
            messages.success(request, f"Purchase Order '{po.po_number}' created successfully.")
            return redirect('purchase_order_detail', pk=po.pk)
    else:
        # Default auto-generated PO number suggestion
        next_po_num = f"PO-2026-{(PurchaseOrder.objects.count() + 1):04d}"
        form = PurchaseOrderForm(initial={'po_number': next_po_num, 'status': PurchaseOrder.Status.SUBMITTED})
        formset = PurchaseOrderItemFormSet()

    return render(request, 'inventory/po_form.html', {
        'page_title': 'Issue New Purchase Order',
        'form': form,
        'formset': formset,
        'back_url': 'purchase_order_list',
    })


@login_required
def purchase_order_approve_view(request, pk):
    if not can_manage_inventory(request.user):
        raise PermissionDenied("You do not have permission to approve purchase orders.")

    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == 'POST':
        po.status = PurchaseOrder.Status.APPROVED
        po.approved_by = request.user
        po.save(update_fields=['status', 'approved_by'])

        log_audit_event(
            action=AuditLogEntry.Action.PO_APPROVED,
            module=AuditLogEntry.Module.INVENTORY,
            object_repr=f"Purchase Order {po.po_number}",
            object_id=str(po.pk),
            reference_number=po.po_number,
            user=request.user,
            request=request,
            details={
                'supplier': po.supplier.name,
                'total_amount': po.total_amount
            }
        )

        messages.success(request, f"Purchase Order '{po.po_number}' has been formally approved.")
    return redirect('purchase_order_detail', pk=po.pk)


# ==============================================================================
# 3. Goods Receipt Notes (GRN / Purchase Receipts)
# ==============================================================================

@login_required
def grn_list_view(request):
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()

    grns = GoodsReceiptNote.objects.select_related('supplier', 'purchase_order', 'received_by')

    if query:
        grns = grns.filter(
            Q(grn_number__icontains=query) |
            Q(supplier__name__icontains=query) |
            Q(supplier_invoice_no__icontains=query)
        )
    if status:
        grns = grns.filter(status=status)

    paginator = Paginator(grns, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'inventory/grn_list.html', {
        'page_title': 'Goods Receipt Notes (Inbound Consignments)',
        'page_obj': page_obj,
        'query': query,
        'status': status,
        'status_choices': GoodsReceiptNote.Status.choices,
        'can_manage': can_manage_inventory(request.user),
    })


@login_required
def grn_detail_view(request, pk):
    grn = get_object_or_404(
        GoodsReceiptNote.objects.select_related('supplier', 'purchase_order', 'received_by'),
        pk=pk
    )
    items = grn.items.select_related('raw_material', 'packaging_material', 'uom').all()

    # Find associated ledger entries
    ledger_entries = StockLedgerEntry.objects.filter(
        reference_type='GRN', reference_id=grn.grn_number
    ).select_related('uom', 'performed_by')

    return render(request, 'inventory/grn_detail.html', {
        'page_title': f"GRN {grn.grn_number} - {grn.supplier.name}",
        'grn': grn,
        'items': items,
        'ledger_entries': ledger_entries,
        'can_manage': can_manage_inventory(request.user),
    })


@login_required
def grn_create_view(request):
    if not can_manage_inventory(request.user):
        raise PermissionDenied("You do not have permission to receive inventory.")

    po_id = request.GET.get('po')
    linked_po = None
    if po_id:
        linked_po = get_object_or_404(PurchaseOrder, pk=po_id)

    if request.method == 'POST':
        form = GoodsReceiptNoteForm(request.POST)
        formset = GoodsReceiptItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                grn = form.save(commit=False)
                grn.received_by = request.user
                if linked_po and not grn.purchase_order:
                    grn.purchase_order = linked_po
                grn.save()
                formset.instance = grn
                formset.save()

            messages.success(request, f"Goods Receipt Note '{grn.grn_number}' recorded. Ready for ledger posting.")
            return redirect('grn_detail', pk=grn.pk)
    else:
        next_grn_num = f"GRN-2026-{(GoodsReceiptNote.objects.count() + 1):04d}"
        initial = {'grn_number': next_grn_num}
        if linked_po:
            initial.update({
                'purchase_order': linked_po,
                'supplier': linked_po.supplier,
            })
        form = GoodsReceiptNoteForm(initial=initial)

        # Prepopulate items from PO if requested
        if linked_po:
            initial_items = []
            for item in linked_po.items.all():
                if item.pending_quantity > Decimal('0.0000'):
                    initial_items.append({
                        'po_item': item,
                        'item_type': item.item_type,
                        'raw_material': item.raw_material,
                        'packaging_material': item.packaging_material,
                        'received_quantity': item.pending_quantity,
                        'rejected_quantity': Decimal('0.0000'),
                        'uom': item.uom,
                        'unit_price': item.unit_price,
                        'batch_number': f"LOT-{item.item_code}-2026",
                    })
            formset = GoodsReceiptItemFormSet(initial=initial_items)
            formset.extra = max(0, len(initial_items) - formset.total_form_count())
        else:
            formset = GoodsReceiptItemFormSet()

    return render(request, 'inventory/grn_form.html', {
        'page_title': 'Record Inbound Material Receipt (GRN)',
        'form': form,
        'formset': formset,
        'linked_po': linked_po,
        'back_url': 'grn_list',
    })


@login_required
def grn_post_view(request, pk):
    """
    Atomically posts a Goods Receipt Note into stock ledger and updates stock items.
    """
    if not can_manage_inventory(request.user):
        raise PermissionDenied("You do not have permission to post inventory receipts.")

    grn = get_object_or_404(GoodsReceiptNote, pk=pk)

    if request.method == 'POST':
        try:
            post_goods_receipt(grn.pk, request.user)
            messages.success(request, f"GRN '{grn.grn_number}' posted successfully! Stock balances and ledger entries updated.")
        except Exception as e:
            messages.error(request, f"Failed to post GRN to inventory: {e}")

    return redirect('grn_detail', pk=grn.pk)


# ==============================================================================
# 4. Current Stock Summary & Low-Stock Alerts
# ==============================================================================

@login_required
def stock_summary_view(request):
    """
    Real-time inventory stock summary showing on-hand quantities, locations,
    batch lots, expiry dates, and low-stock indicators.
    """
    query = request.GET.get('q', '').strip()
    item_type = request.GET.get('type', '').strip()
    filter_low_stock = request.GET.get('low_stock', '').strip()

    items = StockItem.objects.select_related(
        'raw_material', 'packaging_material', 'product_pack_size', 'uom'
    ).order_by('item_type', 'raw_material__name', 'product_pack_size__sku_code')

    if query:
        items = items.filter(
            Q(raw_material__name__icontains=query) |
            Q(raw_material__code__icontains=query) |
            Q(packaging_material__name__icontains=query) |
            Q(packaging_material__code__icontains=query) |
            Q(product_pack_size__sku_code__icontains=query) |
            Q(batch_number__icontains=query)
        )

    if item_type:
        items = items.filter(item_type=item_type)

    item_list = list(items)
    if filter_low_stock == '1':
        item_list = [item for item in item_list if item.is_low_stock]

    paginator = Paginator(item_list, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'inventory/stock_summary.html', {
        'page_title': 'Current Stock Summary & Inventory Valuation',
        'page_obj': page_obj,
        'query': query,
        'item_type': item_type,
        'filter_low_stock': filter_low_stock,
        'type_choices': ItemType.choices,
    })


# ==============================================================================
# 5. Stock Ledger (Traceable Transaction Audit Trail)
# ==============================================================================

@login_required
def stock_ledger_list_view(request):
    """
    Immutable stock ledger: verifies opening + receipts - issues = closing.
    Full audit trail with source reference traceability.
    """
    query = request.GET.get('q', '').strip()
    movement_type = request.GET.get('movement', '').strip()
    item_type = request.GET.get('type', '').strip()

    entries = StockLedgerEntry.objects.select_related(
        'raw_material', 'packaging_material', 'product_pack_size', 'uom', 'performed_by'
    ).order_by('-timestamp', '-id')

    if query:
        entries = entries.filter(
            Q(entry_number__icontains=query) |
            Q(reference_id__icontains=query) |
            Q(batch_number__icontains=query) |
            Q(raw_material__name__icontains=query) |
            Q(packaging_material__name__icontains=query) |
            Q(product_pack_size__sku_code__icontains=query)
        )

    if movement_type:
        entries = entries.filter(movement_type=movement_type)

    if item_type:
        entries = entries.filter(item_type=item_type)

    paginator = Paginator(entries, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'inventory/stock_ledger.html', {
        'page_title': 'Traceable Stock Ledger (Audit Trail)',
        'page_obj': page_obj,
        'query': query,
        'movement_type': movement_type,
        'item_type': item_type,
        'movement_choices': MovementType.choices,
        'type_choices': ItemType.choices,
    })


# ==============================================================================
# 6. Stock Adjustments & Physical Inventory Audits
# ==============================================================================

@login_required
def stock_adjustment_list_view(request):
    query = request.GET.get('q', '').strip()
    adjustments = StockAdjustment.objects.select_related('created_by', 'approved_by')

    if query:
        adjustments = adjustments.filter(
            Q(adjustment_number__icontains=query) | Q(notes__icontains=query)
        )

    paginator = Paginator(adjustments, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'inventory/adjustment_list.html', {
        'page_title': 'Stock Adjustments & Physical Inventory Audits',
        'page_obj': page_obj,
        'query': query,
        'can_manage': can_manage_inventory(request.user),
    })


@login_required
def stock_adjustment_detail_view(request, pk):
    adjustment = get_object_or_404(
        StockAdjustment.objects.select_related('created_by', 'approved_by'),
        pk=pk
    )
    items = adjustment.items.select_related(
        'raw_material', 'packaging_material', 'product_pack_size', 'uom'
    ).all()

    return render(request, 'inventory/adjustment_detail.html', {
        'page_title': f"Audit Adjustment: {adjustment.adjustment_number}",
        'adjustment': adjustment,
        'items': items,
        'can_manage': can_manage_inventory(request.user),
    })


@login_required
def stock_adjustment_create_view(request):
    if not can_manage_inventory(request.user):
        raise PermissionDenied("You do not have permission to execute stock adjustments.")

    if request.method == 'POST':
        form = StockAdjustmentForm(request.POST)
        formset = StockAdjustmentItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                adj = form.save(commit=False)
                adj.created_by = request.user
                adj.save()
                formset.instance = adj
                formset.save()
            messages.success(request, f"Stock Adjustment '{adj.adjustment_number}' recorded. Ready for audit posting.")
            return redirect('stock_adjustment_detail', pk=adj.pk)
    else:
        next_adj_num = f"ADJ-2026-{(StockAdjustment.objects.count() + 1):04d}"
        form = StockAdjustmentForm(initial={'adjustment_number': next_adj_num})
        formset = StockAdjustmentItemFormSet()

    return render(request, 'inventory/adjustment_form.html', {
        'page_title': 'New Physical Inventory Verification / Adjustment',
        'form': form,
        'formset': formset,
        'back_url': 'stock_adjustment_list',
    })


@login_required
def stock_adjustment_post_view(request, pk):
    """
    Applies audited physical counts into stock ledger.
    """
    if not can_manage_inventory(request.user):
        raise PermissionDenied("You do not have permission to post stock adjustments.")

    adjustment = get_object_or_404(StockAdjustment, pk=pk)
    if request.method == 'POST':
        try:
            post_stock_adjustment(adjustment.pk, request.user)
            messages.success(request, f"Stock Adjustment '{adjustment.adjustment_number}' successfully posted to ledger.")
        except Exception as e:
            messages.error(request, f"Failed to post adjustment: {e}")

    return redirect('stock_adjustment_detail', pk=adjustment.pk)
