from django.contrib import admin
from .models import (
    PurchaseOrder,
    PurchaseOrderItem,
    GoodsReceiptNote,
    GoodsReceiptItem,
    StockItem,
    StockLedgerEntry,
    StockAdjustment,
    StockAdjustmentItem,
)


class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 1
    fields = ('item_type', 'raw_material', 'packaging_material', 'ordered_quantity', 'received_quantity', 'uom', 'unit_price', 'line_total')
    readonly_fields = ('line_total',)


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('po_number', 'supplier', 'order_date', 'expected_delivery_date', 'status', 'total_amount', 'created_by')
    list_filter = ('status', 'supplier', 'order_date')
    search_fields = ('po_number', 'supplier__name')
    inlines = [PurchaseOrderItemInline]
    ordering = ('-order_date', '-id')


class GoodsReceiptItemInline(admin.TabularInline):
    model = GoodsReceiptItem
    extra = 1
    fields = ('item_type', 'raw_material', 'packaging_material', 'received_quantity', 'rejected_quantity', 'accepted_quantity', 'uom', 'unit_price', 'batch_number', 'expiry_date')


@admin.register(GoodsReceiptNote)
class GoodsReceiptNoteAdmin(admin.ModelAdmin):
    list_display = ('grn_number', 'supplier', 'purchase_order', 'received_date', 'status', 'is_posted', 'received_by')
    list_filter = ('status', 'is_posted', 'received_date')
    search_fields = ('grn_number', 'supplier__name', 'supplier_invoice_no')
    inlines = [GoodsReceiptItemInline]
    ordering = ('-received_date', '-id')


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ('item_code', 'item_name', 'item_type', 'batch_number', 'quantity_on_hand', 'uom', 'unit_cost', 'total_valuation', 'location', 'expiry_date')
    list_filter = ('item_type', 'location')
    search_fields = ('batch_number', 'raw_material__name', 'packaging_material__name', 'product_pack_size__sku_code')
    ordering = ('item_type', 'raw_material__name')


@admin.register(StockLedgerEntry)
class StockLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ('entry_number', 'timestamp', 'movement_type', 'item_code', 'item_name', 'opening_quantity', 'quantity_change', 'closing_quantity', 'uom', 'reference_id', 'performed_by')
    list_filter = ('movement_type', 'item_type', 'timestamp')
    search_fields = ('entry_number', 'reference_id', 'batch_number', 'raw_material__name', 'packaging_material__name')
    readonly_fields = [f.name for f in StockLedgerEntry._meta.fields]
    ordering = ('-timestamp', '-id')


class StockAdjustmentItemInline(admin.TabularInline):
    model = StockAdjustmentItem
    extra = 1
    fields = ('item_type', 'raw_material', 'packaging_material', 'product_pack_size', 'batch_number', 'uom', 'system_quantity', 'counted_quantity', 'variance_quantity', 'remarks')


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('adjustment_number', 'adjustment_date', 'reason', 'status', 'is_posted', 'created_by')
    list_filter = ('reason', 'status', 'is_posted')
    search_fields = ('adjustment_number', 'notes')
    inlines = [StockAdjustmentItemInline]
    ordering = ('-adjustment_date', '-id')
