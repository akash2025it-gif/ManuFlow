from django.contrib import admin
from .models import ProductionRun, ProductionMaterialConsumption


class ProductionMaterialConsumptionInline(admin.TabularInline):
    model = ProductionMaterialConsumption
    extra = 0
    readonly_fields = ('item_name', 'variance_quantity', 'variance_pct', 'total_cost')
    fields = (
        'item_type',
        'raw_material',
        'packaging_material',
        'uom',
        'planned_quantity',
        'actual_quantity',
        'damaged_quantity',
        'unit_cost',
        'total_cost',
        'variance_quantity',
        'variance_pct',
        'source_batch_number',
    )


@admin.register(ProductionRun)
class ProductionRunAdmin(admin.ModelAdmin):
    list_display = (
        'run_number',
        'product',
        'product_pack_size',
        'status',
        'planned_quantity',
        'actual_output_quantity',
        'yield_variance_pct',
        'is_posted',
        'total_production_cost',
        'unit_cost_per_output',
        'manufacture_date',
    )
    list_filter = ('status', 'is_posted', 'manufacture_date', 'product')
    search_fields = ('run_number', 'batch_number', 'product__name')
    readonly_fields = (
        'expected_output_quantity',
        'yield_variance_quantity',
        'yield_variance_pct',
        'is_yield_alert_triggered',
        'total_material_cost',
        'total_overhead_cost',
        'total_production_cost',
        'unit_cost_per_output',
        'is_posted',
        'posted_at',
        'posted_by',
        'created_at',
        'updated_at',
    )
    inlines = [ProductionMaterialConsumptionInline]
