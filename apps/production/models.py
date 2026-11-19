from decimal import Decimal
from datetime import date
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.master_data.models import (
    Product,
    ProductPackSize,
    BillOfMaterials,
    RawMaterial,
    PackagingMaterial,
    UnitOfMeasurement,
)
from apps.inventory.models import ItemType


class ProductionRun(models.Model):
    """
    Production Run / Work Order tracking BOM batch execution, planned vs actual material consumption,
    yield performance, packaging damage, overhead cost allocation, and traceable inventory movements.
    """
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft / Planned'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress / Floor Execution'
        COMPLETED = 'COMPLETED', 'Completed & Stock Posted'
        CANCELLED = 'CANCELLED', 'Cancelled'

    run_number = models.CharField(
        'Run / Batch Number',
        max_length=40,
        unique=True,
        help_text='Unique identifier e.g. PRUN-2026-0001'
    )
    bill_of_materials = models.ForeignKey(
        BillOfMaterials,
        on_delete=models.PROTECT,
        related_name='production_runs',
        verbose_name='Recipe / BOM'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='production_runs',
        verbose_name='Finished Product'
    )
    product_pack_size = models.ForeignKey(
        ProductPackSize,
        on_delete=models.PROTECT,
        related_name='production_runs',
        verbose_name='Output SKU Pack Size'
    )
    planned_quantity = models.DecimalField(
        'Planned Output Units',
        max_digits=12,
        decimal_places=2,
        default=Decimal('200.00'),
        help_text='Planned number of target output units (e.g. 200 packets)'
    )
    expected_output_quantity = models.DecimalField(
        'Expected Good Output Units',
        max_digits=12,
        decimal_places=2,
        default=Decimal('200.00'),
        help_text='Calculated expected output based on BOM yield recovery percentage'
    )
    actual_output_quantity = models.DecimalField(
        'Actual Good Output Produced',
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Actual good packaged units produced from run'
    )
    damaged_quantity = models.DecimalField(
        'Damaged / Defective Output',
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Rejected or defective finished output units'
    )

    batch_number = models.CharField(
        'Finished Goods Lot / Batch Number',
        max_length=60,
        blank=True,
        help_text='Batch assigned to finished goods inventory (e.g. LOT-FG-MRK200-RUN01)'
    )
    manufacture_date = models.DateField('Production / Mfd Date', default=date.today)
    expiry_date = models.DateField('Batch Expiry Date', null=True, blank=True)

    status = models.CharField(
        'Run Status',
        max_length=25,
        choices=Status.choices,
        default=Status.DRAFT
    )

    # Configurable variance alert threshold (default 3%)
    variance_alert_threshold_pct = models.DecimalField(
        'Variance Alert Threshold (%)',
        max_digits=5,
        decimal_places=2,
        default=Decimal('3.00'),
        help_text='Configurable variance alert tolerance threshold percentage (default 3.00%)'
    )

    # Costing & Overhead Allocations
    labour_cost = models.DecimalField(
        'Direct Labour Overhead (₹)',
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Direct shop floor labour cost allocated to this batch'
    )
    power_gas_cost = models.DecimalField(
        'Gas & Power Overhead (₹)',
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Fuel, frying gas, electricity, and utility overhead allocated'
    )
    other_overhead_cost = models.DecimalField(
        'Other Overhead (₹)',
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Machine depreciation, maintenance, or consumable overhead'
    )

    # Duplicate posting protection & immutable audit trail
    is_posted = models.BooleanField(
        'Inventory Ledger Posted',
        default=False,
        help_text='Prevents duplicate posting to stock ledger'
    )
    posted_at = models.DateTimeField('Posting Timestamp', null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='production_runs_posted',
        verbose_name='Posted By'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='production_runs_created',
        verbose_name='Created By'
    )

    notes = models.TextField('Batch Notes & Observations', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Production Run'
        verbose_name_plural = 'Production Runs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.run_number} - {self.product.name} ({self.get_status_display()})"

    def clean(self):
        if self.run_number:
            self.run_number = self.run_number.strip().upper()
        if self.batch_number:
            self.batch_number = self.batch_number.strip().upper()
        if self.planned_quantity is not None and self.planned_quantity <= Decimal('0.00'):
            raise ValidationError("Planned batch quantity must be strictly greater than 0.")
        if self.actual_output_quantity is not None and self.actual_output_quantity < Decimal('0.00'):
            raise ValidationError("Actual output quantity cannot be negative.")
        if self.variance_alert_threshold_pct is not None and self.variance_alert_threshold_pct < Decimal('0.00'):
            raise ValidationError("Variance alert threshold percentage cannot be negative.")

    def get_absolute_url(self):
        return reverse('production_run_detail', kwargs={'pk': self.pk})

    # --------------------------------------------------------------------------
    # Yield & Variance Calculations
    # --------------------------------------------------------------------------
    @property
    def yield_variance_quantity(self):
        """Variance between actual good output and expected BOM output."""
        return (self.actual_output_quantity - self.expected_output_quantity).quantize(Decimal('0.01'))

    @property
    def yield_variance_pct(self):
        """
        Yield variance percentage = ((Actual - Expected) / Expected) * 100.
        Negative indicates an adverse yield shortfall; positive indicates favorable surplus.
        """
        if self.expected_output_quantity > Decimal('0.00'):
            pct = ((self.actual_output_quantity - self.expected_output_quantity) / self.expected_output_quantity) * Decimal('100.00')
            return pct.quantize(Decimal('0.01'))
        return Decimal('0.00')

    @property
    def is_yield_alert_triggered(self):
        """Checks if yield variance exceeds the configurable tolerance threshold."""
        return abs(self.yield_variance_pct) > self.variance_alert_threshold_pct

    @property
    def material_variance_alerts(self):
        """Returns list of materials whose consumption variance exceeds the alert threshold."""
        alerts = []
        for item in self.materials.all():
            if item.is_variance_alert_triggered:
                alerts.append(item)
        return alerts

    @property
    def has_any_variance_alert(self):
        """True if either the yield variance or any material variance exceeds the alert threshold."""
        if self.is_yield_alert_triggered:
            return True
        return len(self.material_variance_alerts) > 0

    # --------------------------------------------------------------------------
    # Costing & Financial Calculations
    # --------------------------------------------------------------------------
    @property
    def total_material_cost(self):
        """Calculates total cost of actual raw and packaging materials consumed."""
        total = Decimal('0.00')
        for item in self.materials.all():
            total += item.total_cost
        return total.quantize(Decimal('0.01'))

    @property
    def total_overhead_cost(self):
        """Calculates aggregate overhead allocations (Labour + Gas/Power + Other)."""
        return (self.labour_cost + self.power_gas_cost + self.other_overhead_cost).quantize(Decimal('0.01'))

    @property
    def total_production_cost(self):
        """Total manufacturing cost of the batch = Total Materials + Total Overheads."""
        return (self.total_material_cost + self.total_overhead_cost).quantize(Decimal('0.01'))

    @property
    def unit_cost_per_output(self):
        """Unit manufacturing cost per good output unit produced."""
        if self.actual_output_quantity > Decimal('0.00'):
            return (self.total_production_cost / self.actual_output_quantity).quantize(Decimal('0.0001'))
        return Decimal('0.0000')


class ProductionMaterialConsumption(models.Model):
    """
    Ingredient and packaging material consumption line item within a Production Run.
    Tracks planned vs actual consumption, damaged/scrapped packaging, weighted-average costs, and variances.
    """
    production_run = models.ForeignKey(
        ProductionRun,
        on_delete=models.CASCADE,
        related_name='materials',
        verbose_name='Production Run'
    )
    item_type = models.CharField(
        'Item Classification',
        max_length=25,
        choices=ItemType.choices,
        default=ItemType.RAW_MATERIAL
    )
    raw_material = models.ForeignKey(
        RawMaterial,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='production_consumptions',
        verbose_name='Raw Material'
    )
    packaging_material = models.ForeignKey(
        PackagingMaterial,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='production_consumptions',
        verbose_name='Packaging Material'
    )
    uom = models.ForeignKey(
        UnitOfMeasurement,
        on_delete=models.PROTECT,
        related_name='+',
        verbose_name='Unit of Measure'
    )
    planned_quantity = models.DecimalField(
        'Planned Consumption Quantity',
        max_digits=12,
        decimal_places=4,
        help_text='Calculated BOM standard consumption for target output'
    )
    actual_quantity = models.DecimalField(
        'Actual Consumed Quantity',
        max_digits=12,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text='Actual quantity issued and consumed on shop floor'
    )
    damaged_quantity = models.DecimalField(
        'Damaged / Scrapped Quantity',
        max_digits=12,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text='Component units damaged during filling or packaging (e.g. 6 damaged pouches)'
    )
    unit_cost = models.DecimalField(
        'Weighted-Average Unit Cost (₹)',
        max_digits=12,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text='Effective weighted-average inventory unit cost at consumption'
    )
    total_cost = models.DecimalField(
        'Line Total Cost (₹)',
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='actual_quantity * unit_cost'
    )
    source_batch_number = models.CharField(
        'Source Batch / Lot Consumed',
        max_length=60,
        blank=True,
        help_text='Inventory batch from which material was drawn'
    )
    notes = models.CharField('Floor Notes', max_length=200, blank=True)

    class Meta:
        verbose_name = 'Production Material Consumption'
        verbose_name_plural = 'Production Material Consumptions'
        ordering = ['item_type', 'id']

    def __str__(self):
        return f"{self.item_name} - Planned: {self.planned_quantity} {self.uom.code}, Actual: {self.actual_quantity} {self.uom.code}"

    def clean(self):
        if not self.raw_material and not self.packaging_material:
            raise ValidationError("A consumption line must reference either a RawMaterial or a PackagingMaterial.")
        if self.raw_material and self.packaging_material:
            raise ValidationError("Cannot assign both RawMaterial and PackagingMaterial to the same line item.")
        if self.planned_quantity is not None and self.planned_quantity < Decimal('0.0000'):
            raise ValidationError("Planned quantity cannot be negative.")
        if self.actual_quantity is not None and self.actual_quantity < Decimal('0.0000'):
            raise ValidationError("Actual quantity cannot be negative.")
        if self.damaged_quantity is not None and self.damaged_quantity < Decimal('0.0000'):
            raise ValidationError("Damaged quantity cannot be negative.")

    @property
    def item_name(self):
        return self.raw_material.name if self.raw_material else self.packaging_material.name

    @property
    def item_code(self):
        return self.raw_material.code if self.raw_material else self.packaging_material.code

    @property
    def variance_quantity(self):
        """Actual quantity minus planned quantity (positive = overconsumption, negative = saving)."""
        return (self.actual_quantity - self.planned_quantity).quantize(Decimal('0.0001'))

    @property
    def variance_pct(self):
        """
        Variance percentage = ((Actual - Planned) / Planned) * 100.
        E.g., Oil planned 10.0L, actual 10.5L => +5.00%.
        """
        if self.planned_quantity > Decimal('0.0000'):
            pct = ((self.actual_quantity - self.planned_quantity) / self.planned_quantity) * Decimal('100.00')
            return pct.quantize(Decimal('0.01'))
        return Decimal('0.00')

    @property
    def is_variance_alert_triggered(self):
        """Returns True if material consumption variance exceeds the run's alert threshold."""
        threshold = self.production_run.variance_alert_threshold_pct
        return abs(self.variance_pct) > threshold
