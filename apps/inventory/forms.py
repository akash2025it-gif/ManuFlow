from django import forms
from django.forms import inlineformset_factory
from .models import (
    PurchaseOrder,
    PurchaseOrderItem,
    GoodsReceiptNote,
    GoodsReceiptItem,
    StockAdjustment,
    StockAdjustmentItem,
)


class BaseBootstrapModelForm(forms.ModelForm):
    """Auto-injects Bootstrap form classes onto inputs."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-check-input'})
            elif isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                field.widget.attrs.update({'class': 'form-select'})
            else:
                field.widget.attrs.update({'class': 'form-control'})


class PurchaseOrderForm(BaseBootstrapModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ['po_number', 'supplier', 'order_date', 'expected_delivery_date', 'status', 'notes']
        widgets = {
            'order_date': forms.DateInput(attrs={'type': 'date'}),
            'expected_delivery_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }


class PurchaseOrderItemForm(BaseBootstrapModelForm):
    class Meta:
        model = PurchaseOrderItem
        fields = ['item_type', 'raw_material', 'packaging_material', 'ordered_quantity', 'uom', 'unit_price']


PurchaseOrderItemFormSet = inlineformset_factory(
    PurchaseOrder,
    PurchaseOrderItem,
    form=PurchaseOrderItemForm,
    extra=1,
    can_delete=True
)


class GoodsReceiptNoteForm(BaseBootstrapModelForm):
    class Meta:
        model = GoodsReceiptNote
        fields = ['grn_number', 'purchase_order', 'supplier', 'supplier_invoice_no', 'invoice_date', 'received_date', 'notes']
        widgets = {
            'invoice_date': forms.DateInput(attrs={'type': 'date'}),
            'received_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }


class GoodsReceiptItemForm(BaseBootstrapModelForm):
    class Meta:
        model = GoodsReceiptItem
        fields = [
            'item_type', 'raw_material', 'packaging_material', 'received_quantity',
            'rejected_quantity', 'uom', 'unit_price', 'batch_number', 'manufacture_date', 'expiry_date', 'storage_location'
        ]
        widgets = {
            'manufacture_date': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
        }


GoodsReceiptItemFormSet = inlineformset_factory(
    GoodsReceiptNote,
    GoodsReceiptItem,
    form=GoodsReceiptItemForm,
    extra=1,
    can_delete=True
)


class StockAdjustmentForm(BaseBootstrapModelForm):
    class Meta:
        model = StockAdjustment
        fields = ['adjustment_number', 'adjustment_date', 'reason', 'notes']
        widgets = {
            'adjustment_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }


class StockAdjustmentItemForm(BaseBootstrapModelForm):
    class Meta:
        model = StockAdjustmentItem
        fields = [
            'item_type', 'raw_material', 'packaging_material', 'product_pack_size',
            'batch_number', 'uom', 'system_quantity', 'counted_quantity', 'unit_cost', 'remarks'
        ]


StockAdjustmentItemFormSet = inlineformset_factory(
    StockAdjustment,
    StockAdjustmentItem,
    form=StockAdjustmentItemForm,
    extra=1,
    can_delete=True
)
