from django import forms
from django.forms import inlineformset_factory
from .models import (
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


class BaseBootstrapModelForm(forms.ModelForm):
    """Base class to automatically inject Bootstrap form classes onto inputs."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-check-input'})
            elif isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                field.widget.attrs.update({'class': 'form-select'})
            else:
                field.widget.attrs.update({'class': 'form-control'})


class UnitOfMeasurementForm(BaseBootstrapModelForm):
    class Meta:
        model = UnitOfMeasurement
        fields = ['code', 'name', 'uom_type', 'description', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
        }


class UnitConversionForm(BaseBootstrapModelForm):
    class Meta:
        model = UnitConversion
        fields = ['from_uom', 'multiplier', 'to_uom', 'notes']


class SupplierForm(BaseBootstrapModelForm):
    class Meta:
        model = Supplier
        fields = [
            'code', 'name', 'contact_person', 'email', 'phone',
            'tax_id_gst', 'payment_terms', 'address', 'city', 'state', 'is_active'
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 2}),
        }


class CustomerForm(BaseBootstrapModelForm):
    class Meta:
        model = Customer
        fields = [
            'code', 'name', 'customer_type', 'contact_person', 'email', 'phone',
            'tax_id_gst', 'credit_limit', 'credit_days',
            'billing_address', 'shipping_address', 'city', 'state', 'is_active'
        ]
        widgets = {
            'billing_address': forms.Textarea(attrs={'rows': 2}),
            'shipping_address': forms.Textarea(attrs={'rows': 2}),
        }


class RawMaterialForm(BaseBootstrapModelForm):
    class Meta:
        model = RawMaterial
        fields = [
            'code', 'name', 'category', 'uom', 'standard_cost',
            'reorder_level', 'preferred_supplier', 'description', 'is_active'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
        }


class PackagingMaterialForm(BaseBootstrapModelForm):
    class Meta:
        model = PackagingMaterial
        fields = [
            'code', 'name', 'material_type', 'uom', 'standard_cost',
            'reorder_level', 'preferred_supplier', 'is_active'
        ]


class ProductForm(BaseBootstrapModelForm):
    class Meta:
        model = Product
        fields = ['code', 'name', 'category', 'base_uom', 'description', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
        }


class ProductPackSizeForm(BaseBootstrapModelForm):
    class Meta:
        model = ProductPackSize
        fields = [
            'product', 'sku_code', 'pack_name', 'pack_size_value', 'uom',
            'primary_packaging', 'mrp', 'retailer_price', 'distributor_price',
            'barcode', 'is_active'
        ]


class BillOfMaterialsForm(BaseBootstrapModelForm):
    class Meta:
        model = BillOfMaterials
        fields = [
            'product', 'bom_code', 'name', 'version', 'batch_size',
            'output_uom', 'expected_yield_pct', 'is_active_version', 'notes'
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 2}),
        }


class BOMItemForm(BaseBootstrapModelForm):
    class Meta:
        model = BOMItem
        fields = [
            'item_type', 'raw_material', 'packaging_material',
            'quantity', 'uom', 'scrap_tolerance_pct', 'notes'
        ]


# Inline formset for multiple BOM ingredients per finished product formulation
BOMItemFormSet = inlineformset_factory(
    BillOfMaterials,
    BOMItem,
    form=BOMItemForm,
    extra=1,
    can_delete=True
)
