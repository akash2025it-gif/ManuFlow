from django.contrib import admin
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


@admin.register(UnitOfMeasurement)
class UnitOfMeasurementAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'uom_type', 'is_active', 'updated_at')
    list_filter = ('uom_type', 'is_active')
    search_fields = ('code', 'name')
    ordering = ('uom_type', 'code')


@admin.register(UnitConversion)
class UnitConversionAdmin(admin.ModelAdmin):
    list_display = ('from_uom', 'multiplier', 'to_uom', 'notes')
    search_fields = ('from_uom__code', 'to_uom__code')
    ordering = ('from_uom__code',)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'contact_person', 'phone', 'city', 'payment_terms', 'is_active')
    list_filter = ('is_active', 'state')
    search_fields = ('code', 'name', 'contact_person', 'tax_id_gst')
    ordering = ('name',)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'customer_type', 'contact_person', 'phone', 'credit_limit', 'is_active')
    list_filter = ('customer_type', 'is_active', 'state')
    search_fields = ('code', 'name', 'contact_person', 'tax_id_gst')
    ordering = ('name',)


@admin.register(RawMaterial)
class RawMaterialAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'category', 'uom', 'standard_cost', 'reorder_level', 'preferred_supplier', 'is_active')
    list_filter = ('category', 'is_active', 'uom')
    search_fields = ('code', 'name', 'category')
    ordering = ('code',)


@admin.register(PackagingMaterial)
class PackagingMaterialAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'material_type', 'uom', 'standard_cost', 'reorder_level', 'preferred_supplier', 'is_active')
    list_filter = ('material_type', 'is_active', 'uom')
    search_fields = ('code', 'name')
    ordering = ('code',)


class ProductPackSizeInline(admin.TabularInline):
    model = ProductPackSize
    extra = 1
    fields = ('sku_code', 'pack_name', 'pack_size_value', 'uom', 'mrp', 'retailer_price', 'distributor_price', 'is_active')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'category', 'base_uom', 'is_active', 'created_at')
    list_filter = ('category', 'is_active', 'base_uom')
    search_fields = ('code', 'name', 'description')
    inlines = [ProductPackSizeInline]
    ordering = ('code',)


@admin.register(ProductPackSize)
class ProductPackSizeAdmin(admin.ModelAdmin):
    list_display = ('sku_code', 'product', 'pack_name', 'pack_size_value', 'uom', 'mrp', 'retailer_price', 'distributor_price', 'is_active')
    list_filter = ('is_active', 'uom', 'product')
    search_fields = ('sku_code', 'pack_name', 'barcode', 'product__name')
    ordering = ('product', 'pack_size_value')


class BOMItemInline(admin.TabularInline):
    model = BOMItem
    extra = 1
    fields = ('item_type', 'raw_material', 'packaging_material', 'quantity', 'uom', 'scrap_tolerance_pct', 'notes')


@admin.register(BillOfMaterials)
class BillOfMaterialsAdmin(admin.ModelAdmin):
    list_display = ('bom_code', 'name', 'product', 'version', 'batch_size', 'output_uom', 'expected_yield_pct', 'is_active_version')
    list_filter = ('is_active_version', 'output_uom', 'product')
    search_fields = ('bom_code', 'name', 'product__name')
    inlines = [BOMItemInline]
    ordering = ('product', '-version')


@admin.register(BOMItem)
class BOMItemAdmin(admin.ModelAdmin):
    list_display = ('bom', 'item_type', 'ingredient_name', 'quantity', 'uom', 'scrap_tolerance_pct')
    list_filter = ('item_type', 'uom')
    search_fields = ('bom__bom_code', 'raw_material__name', 'packaging_material__name')
