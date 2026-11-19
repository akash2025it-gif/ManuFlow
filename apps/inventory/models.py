from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from apps.master_data.models import (
    Supplier,
    RawMaterial,
    PackagingMaterial,
    ProductPackSize,
    UnitOfMeasurement,
)


class ItemType(models.TextChoices):
    RAW_MATERIAL = 'RAW_MATERIAL', 'Raw Material'
    PACKAGING_MATERIAL = 'PACKAGING_MATERIAL', 'Packaging Material'
    FINISHED_GOODS = 'FINISHED_GOODS', 'Finished Goods SKU'


class MovementType(models.TextChoices):
    OPENING_BALANCE = 'OPENING_BALANCE', 'Opening Stock Balance'
    PURCHASE_RECEIPT = 'PURCHASE_RECEIPT', 'Supplier Purchase Receipt (GRN)'
    PRODUCTION_CONSUMPTION = 'PRODUCTION_CONSUMPTION', 'Issued to Production'
    PRODUCTION_RECEIPT = 'PRODUCTION_RECEIPT', 'Finished Goods Production Receipt'
    SALES_DISPATCH = 'SALES_DISPATCH', 'Sales Order Dispatch'
    STOCK_ADJUSTMENT_IN = 'STOCK_ADJUSTMENT_IN', 'Stock Adjustment (Gain/Found)'
    STOCK_ADJUSTMENT_OUT = 'STOCK_ADJUSTMENT_OUT', 'Stock Adjustment (Loss/Damage)'
    SCRAP_WRITEOFF = 'SCRAP_WRITEOFF', 'Scrap / Expired Write-off'


class PurchaseOrder(models.Model):
    """
    Purchase Order (PO) issued to approved suppliers for raw ingredients and packaging materials.
    """
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        SUBMITTED = 'SUBMITTED', 'Submitted'
        APPROVED = 'APPROVED', 'Approved'
        PARTIALLY_RECEIVED = 'PARTIALLY_RECEIVED', 'Partially Received'
        RECEIVED = 'RECEIVED', 'Fully Received'
        CANCELLED = 'CANCELLED', 'Cancelled'

    po_number = models.CharField('PO Number', max_length=40, unique=True, help_text='e.g. PO-2026-0001')
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='purchase_orders',
        verbose_name='Supplier'
    )
    order_date = models.DateField('Order Date')
    expected_delivery_date = models.DateField('Expected Delivery Date', null=True, blank=True)
    status = models.CharField('Status', max_length=25, choices=Status.choices, default=Status.DRAFT)
    total_amount = models.DecimalField(
        'Total Order Value (₹)',
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00')
    )
    notes = models.TextField('Order Notes / Terms', blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='purchase_orders_created',
        verbose_name='Created By'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_orders_approved',
        verbose_name='Approved By'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Purchase Order'
        verbose_name_plural = 'Purchase Orders'
        ordering = ['-order_date', '-id']

    def __str__(self):
        return f"{self.po_number} - {self.supplier.name} ({self.get_status_display()})"

    def clean(self):
        if self.po_number:
            self.po_number = self.po_number.strip().upper()

    def update_totals(self):
        """Recalculates the total PO amount and updates status based on receipts."""
        total = sum((item.line_total for item in self.items.all()), Decimal('0.00'))
        self.total_amount = total

        # Check receipt status
        items = list(self.items.all())
        if items and self.status not in [self.Status.DRAFT, self.Status.CANCELLED]:
            all_received = all(item.received_quantity >= item.ordered_quantity for item in items)
            any_received = any(item.received_quantity > Decimal('0.0000') for item in items)
            if all_received:
                self.status = self.Status.RECEIVED
            elif any_received:
                self.status = self.Status.PARTIALLY_RECEIVED
        self.save(update_fields=['total_amount', 'status'])


class PurchaseOrderItem(models.Model):
    """
    Line items within a Purchase Order.
    """
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Purchase Order'
    )
    item_type = models.CharField(
        'Item Classification',
        max_length=25,
        choices=[(ItemType.RAW_MATERIAL, 'Raw Material'), (ItemType.PACKAGING_MATERIAL, 'Packaging Material')],
        default=ItemType.RAW_MATERIAL
    )
    raw_material = models.ForeignKey(
        RawMaterial,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='po_items',
        verbose_name='Raw Material'
    )
    packaging_material = models.ForeignKey(
        PackagingMaterial,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='po_items',
        verbose_name='Packaging Material'
    )
    ordered_quantity = models.DecimalField('Ordered Qty', max_digits=12, decimal_places=4)
    received_quantity = models.DecimalField(
        'Received Qty',
        max_digits=12,
        decimal_places=4,
        default=Decimal('0.0000')
    )
    uom = models.ForeignKey(
        UnitOfMeasurement,
        on_delete=models.PROTECT,
        related_name='po_items',
        verbose_name='Unit of Measure'
    )
    unit_price = models.DecimalField('Unit Price (₹)', max_digits=12, decimal_places=2)
    line_total = models.DecimalField('Line Total (₹)', max_digits=14, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        verbose_name = 'Purchase Order Line Item'
        verbose_name_plural = 'Purchase Order Line Items'

    def __str__(self):
        return f"{self.item_name}: {self.ordered_quantity} {self.uom.code}"

    def clean(self):
        if self.item_type == ItemType.RAW_MATERIAL and not self.raw_material:
            raise ValidationError({'raw_material': 'Raw material must be selected.'})
        if self.item_type == ItemType.PACKAGING_MATERIAL and not self.packaging_material:
            raise ValidationError({'packaging_material': 'Packaging material must be selected.'})
        if self.ordered_quantity is not None and self.ordered_quantity <= Decimal('0.0000'):
            raise ValidationError({'ordered_quantity': 'Ordered quantity must be greater than zero.'})
        if self.unit_price is not None and self.unit_price < Decimal('0.00'):
            raise ValidationError({'unit_price': 'Unit price cannot be negative.'})

    def save(self, *args, **kwargs):
        if self.ordered_quantity and self.unit_price:
            self.line_total = (self.ordered_quantity * self.unit_price).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)

    @property
    def item_name(self):
        if self.item_type == ItemType.RAW_MATERIAL and self.raw_material:
            return self.raw_material.name
        elif self.item_type == ItemType.PACKAGING_MATERIAL and self.packaging_material:
            return self.packaging_material.name
        return "Unknown Item"

    @property
    def item_code(self):
        if self.item_type == ItemType.RAW_MATERIAL and self.raw_material:
            return self.raw_material.code
        elif self.item_type == ItemType.PACKAGING_MATERIAL and self.packaging_material:
            return self.packaging_material.code
        return "-"

    @property
    def pending_quantity(self):
        return max(Decimal('0.0000'), self.ordered_quantity - self.received_quantity)


class GoodsReceiptNote(models.Model):
    """
    Goods Receipt Note (GRN) / Purchase Receipt for inbound material consignments.
    Posting this document atomically updates inventory balances and records stock movements.
    """
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft (Inspection Pending)'
        POSTED = 'POSTED', 'Verified & Posted to Stock'
        CANCELLED = 'CANCELLED', 'Cancelled'

    grn_number = models.CharField('GRN Number', max_length=40, unique=True, help_text='e.g. GRN-2026-0001')
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='receipts',
        verbose_name='Reference Purchase Order'
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='grn_receipts',
        verbose_name='Supplier'
    )
    supplier_invoice_no = models.CharField('Vendor Invoice / Challan No', max_length=60, blank=True)
    invoice_date = models.DateField('Invoice / Challan Date', null=True, blank=True)
    received_date = models.DateField('Material Received Date')
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='grns_received',
        verbose_name='Store Officer / Receiver'
    )
    status = models.CharField('GRN Status', max_length=25, choices=Status.choices, default=Status.DRAFT)
    is_posted = models.BooleanField('Posted to Ledger', default=False, help_text='Prevents duplicate posting')
    posted_at = models.DateTimeField('Posted Timestamp', null=True, blank=True)
    notes = models.TextField('Inspection & Quality Notes', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Goods Receipt Note (GRN)'
        verbose_name_plural = 'Goods Receipt Notes (GRNs)'
        ordering = ['-received_date', '-id']

    def __str__(self):
        return f"{self.grn_number} - {self.supplier.name} ({self.get_status_display()})"

    def clean(self):
        if self.grn_number:
            self.grn_number = self.grn_number.strip().upper()


class GoodsReceiptItem(models.Model):
    """
    Line items received under a Goods Receipt Note.
    Captures batch number, manufacture date, expiry date, accepted vs rejected quantities.
    """
    grn = models.ForeignKey(
        GoodsReceiptNote,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='GRN Reference'
    )
    po_item = models.ForeignKey(
        PurchaseOrderItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='grn_items',
        verbose_name='PO Line Reference'
    )
    item_type = models.CharField(
        'Item Classification',
        max_length=25,
        choices=[(ItemType.RAW_MATERIAL, 'Raw Material'), (ItemType.PACKAGING_MATERIAL, 'Packaging Material')],
        default=ItemType.RAW_MATERIAL
    )
    raw_material = models.ForeignKey(
        RawMaterial,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='grn_items',
        verbose_name='Raw Material'
    )
    packaging_material = models.ForeignKey(
        PackagingMaterial,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='grn_items',
        verbose_name='Packaging Material'
    )
    received_quantity = models.DecimalField('Challan / Delivered Qty', max_digits=12, decimal_places=4)
    rejected_quantity = models.DecimalField(
        'QA Rejected Qty',
        max_digits=12,
        decimal_places=4,
        default=Decimal('0.0000')
    )
    accepted_quantity = models.DecimalField('Accepted Inventory Qty', max_digits=12, decimal_places=4)
    uom = models.ForeignKey(
        UnitOfMeasurement,
        on_delete=models.PROTECT,
        related_name='grn_items',
        verbose_name='Receipt Unit'
    )
    unit_price = models.DecimalField('Unit Cost (₹)', max_digits=12, decimal_places=2)
    batch_number = models.CharField(
        'Lot / Batch Number',
        max_length=60,
        help_text='Vendor lot number or internal receipt batch'
    )
    manufacture_date = models.DateField('Manufacturing Date', null=True, blank=True)
    expiry_date = models.DateField('Expiry / Best Before Date', null=True, blank=True)
    storage_location = models.CharField('Warehouse Bay', max_length=100, default='Central Warehouse')

    class Meta:
        verbose_name = 'GRN Line Item'
        verbose_name_plural = 'GRN Line Items'

    def __str__(self):
        return f"{self.item_name} (Batch: {self.batch_number}): {self.accepted_quantity} {self.uom.code}"

    def clean(self):
        if self.item_type == ItemType.RAW_MATERIAL and not self.raw_material:
            raise ValidationError({'raw_material': 'Raw material must be selected.'})
        if self.item_type == ItemType.PACKAGING_MATERIAL and not self.packaging_material:
            raise ValidationError({'packaging_material': 'Packaging material must be selected.'})
        if self.received_quantity is not None and self.received_quantity <= Decimal('0.0000'):
            raise ValidationError({'received_quantity': 'Received quantity must be greater than zero.'})
        if self.rejected_quantity is not None and self.rejected_quantity < Decimal('0.0000'):
            raise ValidationError({'rejected_quantity': 'Rejected quantity cannot be negative.'})
        if self.received_quantity and self.rejected_quantity:
            if self.rejected_quantity > self.received_quantity:
                raise ValidationError({'rejected_quantity': 'Rejected quantity cannot exceed received quantity.'})

        # Calculate accepted quantity automatically
        if self.received_quantity is not None and self.rejected_quantity is not None:
            self.accepted_quantity = self.received_quantity - self.rejected_quantity

        if not self.batch_number:
            raise ValidationError({'batch_number': 'Lot / Batch number is required for traceability.'})

    def save(self, *args, **kwargs):
        if self.received_quantity is not None and self.rejected_quantity is not None:
            self.accepted_quantity = self.received_quantity - self.rejected_quantity
        if self.batch_number:
            self.batch_number = self.batch_number.strip().upper()
        super().save(*args, **kwargs)

    @property
    def item_name(self):
        if self.item_type == ItemType.RAW_MATERIAL and self.raw_material:
            return self.raw_material.name
        elif self.item_type == ItemType.PACKAGING_MATERIAL and self.packaging_material:
            return self.packaging_material.name
        return "Unknown Item"

    @property
    def item_code(self):
        if self.item_type == ItemType.RAW_MATERIAL and self.raw_material:
            return self.raw_material.code
        elif self.item_type == ItemType.PACKAGING_MATERIAL and self.packaging_material:
            return self.packaging_material.code
        return "-"


class StockItem(models.Model):
    """
    Real-time current stock on hand balance for each material, SKU, and batch.
    """
    item_type = models.CharField('Item Classification', max_length=25, choices=ItemType.choices)
    raw_material = models.ForeignKey(
        RawMaterial,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='stock_records'
    )
    packaging_material = models.ForeignKey(
        PackagingMaterial,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='stock_records'
    )
    product_pack_size = models.ForeignKey(
        ProductPackSize,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='stock_records'
    )
    batch_number = models.CharField('Batch / Lot', max_length=60, blank=True, default='')
    expiry_date = models.DateField('Expiry Date', null=True, blank=True)
    quantity_on_hand = models.DecimalField(
        'Stock On Hand',
        max_digits=14,
        decimal_places=4,
        default=Decimal('0.0000')
    )
    uom = models.ForeignKey(
        UnitOfMeasurement,
        on_delete=models.PROTECT,
        related_name='stock_records',
        verbose_name='Stock Unit'
    )
    unit_cost = models.DecimalField('Valuation Unit Cost (₹)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    location = models.CharField('Storage Location', max_length=100, default='Central Warehouse')
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Inventory Stock Item'
        verbose_name_plural = 'Inventory Stock Items'
        ordering = ['item_type', 'batch_number']
        unique_together = ('item_type', 'raw_material', 'packaging_material', 'product_pack_size', 'batch_number', 'location')

    def __str__(self):
        return f"{self.item_name} [{self.batch_number or 'Standard'}]: {self.quantity_on_hand} {self.uom.code}"

    @property
    def item_name(self):
        if self.item_type == ItemType.RAW_MATERIAL and self.raw_material:
            return self.raw_material.name
        elif self.item_type == ItemType.PACKAGING_MATERIAL and self.packaging_material:
            return self.packaging_material.name
        elif self.item_type == ItemType.FINISHED_GOODS and self.product_pack_size:
            return f"{self.product_pack_size.product.name} ({self.product_pack_size.pack_name})"
        return "Unknown Item"

    @property
    def item_code(self):
        if self.item_type == ItemType.RAW_MATERIAL and self.raw_material:
            return self.raw_material.code
        elif self.item_type == ItemType.PACKAGING_MATERIAL and self.packaging_material:
            return self.packaging_material.code
        elif self.item_type == ItemType.FINISHED_GOODS and self.product_pack_size:
            return self.product_pack_size.sku_code
        return "-"

    @property
    def total_valuation(self):
        return (self.quantity_on_hand * self.unit_cost).quantize(Decimal('0.01'))

    @property
    def is_low_stock(self):
        if self.item_type == ItemType.RAW_MATERIAL and self.raw_material:
            return self.quantity_on_hand <= self.raw_material.reorder_level
        elif self.item_type == ItemType.PACKAGING_MATERIAL and self.packaging_material:
            return self.quantity_on_hand <= self.packaging_material.reorder_level
        return False


class StockLedgerEntry(models.Model):
    """
    Immutable, fully auditable record of every stock movement.
    Guarantees:
    1. Every movement has a source reference.
    2. opening_quantity + quantity_change = closing_quantity.
    3. closing_quantity cannot be negative.
    4. Opening + receipts - issues = closing integrity.
    """
    entry_number = models.CharField('Transaction ID', max_length=50, unique=True, help_text='e.g. TXN-STK-2026-00001')
    timestamp = models.DateTimeField('Movement Timestamp', auto_now_add=True)
    movement_type = models.CharField('Movement Type', max_length=30, choices=MovementType.choices)
    item_type = models.CharField('Item Classification', max_length=25, choices=ItemType.choices)

    raw_material = models.ForeignKey(RawMaterial, on_delete=models.PROTECT, null=True, blank=True, related_name='ledger_entries')
    packaging_material = models.ForeignKey(PackagingMaterial, on_delete=models.PROTECT, null=True, blank=True, related_name='ledger_entries')
    product_pack_size = models.ForeignKey(ProductPackSize, on_delete=models.PROTECT, null=True, blank=True, related_name='ledger_entries')

    batch_number = models.CharField('Batch / Lot', max_length=60, blank=True, default='')
    expiry_date = models.DateField('Expiry Date', null=True, blank=True)
    uom = models.ForeignKey(UnitOfMeasurement, on_delete=models.PROTECT, related_name='ledger_entries')

    opening_quantity = models.DecimalField('Opening Stock Qty', max_digits=14, decimal_places=4)
    quantity_change = models.DecimalField(
        'Quantity Delta',
        max_digits=14,
        decimal_places=4,
        help_text='Positive for receipts/gains, negative for issues/losses'
    )
    closing_quantity = models.DecimalField('Closing Stock Qty', max_digits=14, decimal_places=4)

    unit_cost = models.DecimalField('Unit Valuation (₹)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_value = models.DecimalField('Transaction Value (₹)', max_digits=14, decimal_places=2, default=Decimal('0.00'))

    reference_type = models.CharField('Source Document Type', max_length=50, help_text='GRN, PO, ADJUSTMENT, OPENING, DISPATCH')
    reference_id = models.CharField('Source Reference ID', max_length=60, help_text='Document Number')
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='stock_movements',
        verbose_name='Executed By'
    )
    remarks = models.TextField('Transaction Remarks', blank=True)

    class Meta:
        verbose_name = 'Stock Ledger Movement Entry'
        verbose_name_plural = 'Stock Ledger Movement Entries'
        ordering = ['-timestamp', '-id']

    def __str__(self):
        return f"{self.entry_number}: {self.get_movement_type_display()} ({self.quantity_change} {self.uom.code})"

    def clean(self):
        expected_closing = (self.opening_quantity + self.quantity_change).quantize(Decimal('0.0001'))
        if self.closing_quantity is not None and self.closing_quantity != expected_closing:
            raise ValidationError(
                f"Ledger balance violation: Opening ({self.opening_quantity}) + Change ({self.quantity_change}) "
                f"must equal Closing ({expected_closing}), but got {self.closing_quantity}."
            )
        if self.closing_quantity is not None and self.closing_quantity < Decimal('0.0000'):
            raise ValidationError(
                f"Negative stock prohibited! Transaction would result in negative closing balance: {self.closing_quantity}."
            )

    @property
    def item_name(self):
        if self.item_type == ItemType.RAW_MATERIAL and self.raw_material:
            return self.raw_material.name
        elif self.item_type == ItemType.PACKAGING_MATERIAL and self.packaging_material:
            return self.packaging_material.name
        elif self.item_type == ItemType.FINISHED_GOODS and self.product_pack_size:
            return f"{self.product_pack_size.product.name} ({self.product_pack_size.pack_name})"
        return "Unknown Item"

    @property
    def item_code(self):
        if self.item_type == ItemType.RAW_MATERIAL and self.raw_material:
            return self.raw_material.code
        elif self.item_type == ItemType.PACKAGING_MATERIAL and self.packaging_material:
            return self.packaging_material.code
        elif self.item_type == ItemType.FINISHED_GOODS and self.product_pack_size:
            return self.product_pack_size.sku_code
        return "-"


class StockAdjustment(models.Model):
    """
    Physical inventory verification audit and reconciliation record.
    Posting this document applies variances into the ledger and updates stock.
    """
    class Reason(models.TextChoices):
        PHYSICAL_AUDIT = 'PHYSICAL_AUDIT', 'Physical Inventory Verification / Periodic Audit'
        DAMAGE_EXPIRY = 'DAMAGE_EXPIRY', 'Damaged / Spoilage / Expired Goods Write-off'
        MOISTURE_LOSS = 'MOISTURE_LOSS', 'Moisture Loss / Inherent Process Evaporation'
        UOM_CONVERSION = 'UOM_CONVERSION', 'Repackaging & UOM Recalibration'
        OTHER = 'OTHER', 'Other Discrepancy Adjustment'

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft (Audit in Progress)'
        POSTED = 'POSTED', 'Audited & Approved Posted'
        CANCELLED = 'CANCELLED', 'Cancelled'

    adjustment_number = models.CharField('Adjustment Number', max_length=40, unique=True, help_text='e.g. ADJ-2026-0001')
    adjustment_date = models.DateField('Audit Date')
    reason = models.CharField('Reason for Adjustment', max_length=30, choices=Reason.choices, default=Reason.PHYSICAL_AUDIT)
    status = models.CharField('Status', max_length=20, choices=Status.choices, default=Status.DRAFT)
    is_posted = models.BooleanField('Posted to Ledger', default=False)
    posted_at = models.DateTimeField('Posted Timestamp', null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='stock_adjustments_created',
        verbose_name='Audited By'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_adjustments_approved',
        verbose_name='Approved By'
    )
    notes = models.TextField('Audit Observations', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Stock Adjustment'
        verbose_name_plural = 'Stock Adjustments'
        ordering = ['-adjustment_date', '-id']

    def __str__(self):
        return f"{self.adjustment_number} ({self.get_reason_display()})"

    def clean(self):
        if self.adjustment_number:
            self.adjustment_number = self.adjustment_number.strip().upper()


class StockAdjustmentItem(models.Model):
    """
    Line items within a Stock Adjustment.
    Captures system quantity vs physical counted quantity, computing variance.
    """
    adjustment = models.ForeignKey(
        StockAdjustment,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Adjustment Reference'
    )
    item_type = models.CharField('Item Classification', max_length=25, choices=ItemType.choices)
    raw_material = models.ForeignKey(RawMaterial, on_delete=models.PROTECT, null=True, blank=True)
    packaging_material = models.ForeignKey(PackagingMaterial, on_delete=models.PROTECT, null=True, blank=True)
    product_pack_size = models.ForeignKey(ProductPackSize, on_delete=models.PROTECT, null=True, blank=True)

    batch_number = models.CharField('Batch / Lot', max_length=60, blank=True, default='')
    uom = models.ForeignKey(UnitOfMeasurement, on_delete=models.PROTECT, verbose_name='Measurement Unit')

    system_quantity = models.DecimalField('System Recorded Stock', max_digits=14, decimal_places=4)
    counted_quantity = models.DecimalField('Physical Counted Qty', max_digits=14, decimal_places=4)
    variance_quantity = models.DecimalField(
        'Stock Variance',
        max_digits=14,
        decimal_places=4,
        help_text='Variance = Counted - System (Positive = Gain, Negative = Shortage)'
    )
    unit_cost = models.DecimalField('Standard Unit Cost (₹)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    remarks = models.CharField('Variance Explanation', max_length=200, blank=True)

    class Meta:
        verbose_name = 'Stock Adjustment Line'
        verbose_name_plural = 'Stock Adjustment Lines'

    def __str__(self):
        return f"{self.item_name}: Variance {self.variance_quantity} {self.uom.code}"

    def clean(self):
        if self.counted_quantity is not None and self.counted_quantity < Decimal('0.0000'):
            raise ValidationError({'counted_quantity': 'Physical counted quantity cannot be negative.'})
        if self.counted_quantity is not None and self.system_quantity is not None:
            self.variance_quantity = self.counted_quantity - self.system_quantity

    def save(self, *args, **kwargs):
        if self.counted_quantity is not None and self.system_quantity is not None:
            self.variance_quantity = self.counted_quantity - self.system_quantity
        super().save(*args, **kwargs)

    @property
    def item_name(self):
        if self.item_type == ItemType.RAW_MATERIAL and self.raw_material:
            return self.raw_material.name
        elif self.item_type == ItemType.PACKAGING_MATERIAL and self.packaging_material:
            return self.packaging_material.name
        elif self.item_type == ItemType.FINISHED_GOODS and self.product_pack_size:
            return f"{self.product_pack_size.product.name} ({self.product_pack_size.pack_name})"
        return "Unknown Item"

    @property
    def item_code(self):
        if self.item_type == ItemType.RAW_MATERIAL and self.raw_material:
            return self.raw_material.code
        elif self.item_type == ItemType.PACKAGING_MATERIAL and self.packaging_material:
            return self.packaging_material.code
        elif self.item_type == ItemType.FINISHED_GOODS and self.product_pack_size:
            return self.product_pack_size.sku_code
        return "-"
