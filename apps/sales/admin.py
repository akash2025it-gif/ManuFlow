from django.contrib import admin
from .models import SalesOrder, SalesOrderItem, Invoice, Dispatch, PaymentRecord


class SalesOrderItemInline(admin.TabularInline):
    model = SalesOrderItem
    extra = 0
    fields = [
        'product_pack_size',
        'quantity',
        'uom',
        'unit_price',
        'subtotal',
        'cgst_amount',
        'sgst_amount',
        'igst_amount',
        'total_price',
        'dispatched_quantity',
    ]
    readonly_fields = [
        'subtotal',
        'cgst_amount',
        'sgst_amount',
        'igst_amount',
        'total_price',
    ]


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = [
        'order_number',
        'customer',
        'salesman',
        'order_date',
        'status',
        'delivery_state',
        'is_interstate',
        'subtotal_amount',
        'total_tax_amount',
        'total_amount',
    ]
    list_filter = ['status', 'is_interstate', 'order_date', 'delivery_state']
    search_fields = ['order_number', 'customer__name', 'customer__code', 'contact_person']
    readonly_fields = [
        'is_interstate',
        'subtotal_amount',
        'cgst_amount',
        'sgst_amount',
        'igst_amount',
        'total_tax_amount',
        'total_amount',
        'approved_by',
        'approved_at',
        'created_at',
        'updated_at',
    ]
    inlines = [SalesOrderItemInline]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        'invoice_number',
        'customer_name',
        'sales_order',
        'invoice_date',
        'taxable_amount',
        'total_tax',
        'grand_total',
        'payment_status',
        'amount_paid',
    ]
    list_filter = ['payment_status', 'is_interstate', 'invoice_date']
    search_fields = ['invoice_number', 'customer_name', 'customer_gstin', 'sales_order__order_number']
    readonly_fields = [
        'taxable_amount',
        'cgst_amount',
        'sgst_amount',
        'igst_amount',
        'total_tax',
        'grand_total',
        'created_at',
        'updated_at',
    ]


@admin.register(Dispatch)
class DispatchAdmin(admin.ModelAdmin):
    list_display = [
        'dispatch_number',
        'sales_order',
        'dispatch_date',
        'carrier_name',
        'vehicle_number',
        'lr_number',
        'status',
        'is_posted',
    ]
    list_filter = ['status', 'is_posted', 'dispatch_date']
    search_fields = ['dispatch_number', 'sales_order__order_number', 'carrier_name', 'vehicle_number', 'lr_number']
    readonly_fields = ['is_posted', 'posted_at', 'created_at', 'updated_at']


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = [
        'payment_number',
        'invoice',
        'customer',
        'payment_date',
        'amount',
        'payment_mode',
        'transaction_reference',
    ]
    list_filter = ['payment_mode', 'payment_date']
    search_fields = ['payment_number', 'invoice__invoice_number', 'customer__name', 'transaction_reference']
    readonly_fields = ['created_at']
