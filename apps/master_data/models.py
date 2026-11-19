from decimal import Decimal
from django.db import models
from django.core.exceptions import ValidationError
from django.urls import reverse


class UnitOfMeasurement(models.Model):
    """
    Standard Units of Measurement (UOM) for inventory, production recipes, and sales packaging.
    """
    class UOMType(models.TextChoices):
        WEIGHT = 'WEIGHT', 'Weight / Mass'
        VOLUME = 'VOLUME', 'Liquid Volume'
        COUNT = 'COUNT', 'Quantity / Count / Pieces'
        LENGTH = 'LENGTH', 'Length / Dimension'
        PACKAGING = 'PACKAGING', 'Secondary Packaging Unit'

    code = models.CharField('UOM Code', max_length=15, unique=True, help_text='Unique symbol e.g. KG, L, G, ML, PCS, BOX')
    name = models.CharField('Unit Name', max_length=50, help_text='Full unit name e.g. Kilogram, Litre, Pieces')
    uom_type = models.CharField('Category', max_length=20, choices=UOMType.choices, default=UOMType.COUNT)
    description = models.CharField('Description', max_length=200, blank=True)
    is_active = models.BooleanField('Active', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Unit of Measurement'
        verbose_name_plural = 'Units of Measurement'
        ordering = ['uom_type', 'code']

    def __str__(self):
        return f"{self.code} ({self.name})"

    def clean(self):
        if self.code:
            self.code = self.code.strip().upper()


class UnitConversion(models.Model):
    """
    Unit conversions (e.g. 1 KG = 1000 G, 1 DRUM = 200 L, 1 BOX = 24 PCS).
    Formula: To Quantity = From Quantity * Multiplier
    """
    from_uom = models.ForeignKey(
        UnitOfMeasurement,
        on_delete=models.CASCADE,
        related_name='conversions_from',
        verbose_name='Source Unit (From)'
    )
    to_uom = models.ForeignKey(
        UnitOfMeasurement,
        on_delete=models.CASCADE,
        related_name='conversions_to',
        verbose_name='Target Unit (To)'
    )
    multiplier = models.DecimalField(
        'Conversion Multiplier',
        max_digits=14,
        decimal_places=6,
        help_text='Multiplier value such that 1 [From UOM] = [Multiplier] * [To UOM]'
    )
    notes = models.CharField('Conversion Notes', max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Unit Conversion'
        verbose_name_plural = 'Unit Conversions'
        unique_together = ('from_uom', 'to_uom')
        ordering = ['from_uom__code', 'to_uom__code']

    def __str__(self):
        return f"1 {self.from_uom.code} = {self.multiplier} {self.to_uom.code}"

    def clean(self):
        if self.from_uom_id and self.to_uom_id and self.from_uom_id == self.to_uom_id:
            raise ValidationError("A unit cannot be converted into itself.")
        if self.multiplier is not None and self.multiplier <= Decimal('0.000000'):
            raise ValidationError("Conversion multiplier must be strictly positive (> 0).")


class Supplier(models.Model):
    """
    Approved vendors supplying raw chemicals, additives, packaging, and factory consumables.
    """
    code = models.CharField('Supplier Code', max_length=30, unique=True, help_text='Unique identifier e.g. SUP-001')
    name = models.CharField('Company / Trade Name', max_length=150)
    contact_person = models.CharField('Primary Contact Person', max_length=100, blank=True)
    email = models.EmailField('Business Email', blank=True)
    phone = models.CharField('Phone Number', max_length=30, blank=True)
    tax_id_gst = models.CharField('GSTIN / Tax ID', max_length=30, blank=True, help_text='15-character GST identification or tax number')
    address = models.TextField('Street Address', blank=True)
    city = models.CharField('City', max_length=100, blank=True)
    state = models.CharField('State / Province', max_length=100, blank=True)
    payment_terms = models.CharField('Payment Terms', max_length=100, default='Net 30 Days')
    is_active = models.BooleanField('Active Status', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Supplier'
        verbose_name_plural = 'Suppliers'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"

    def clean(self):
        if self.code:
            self.code = self.code.strip().upper()


class Customer(models.Model):
    """
    Commercial clients categorized as Retailers or Wholesale Distributors.
    """
    class CustomerType(models.TextChoices):
        RETAILER = 'RETAILER', 'Retailer'
        DISTRIBUTOR = 'DISTRIBUTOR', 'Distributor'

    customer_type = models.CharField('Client Type', max_length=20, choices=CustomerType.choices, default=CustomerType.RETAILER)
    code = models.CharField('Customer Code', max_length=30, unique=True, help_text='Unique identifier e.g. CUST-101')
    name = models.CharField('Enterprise / Entity Name', max_length=150)
    contact_person = models.CharField('Key Account Contact', max_length=100, blank=True)
    email = models.EmailField('Billing Email', blank=True)
    phone = models.CharField('Phone Number', max_length=30, blank=True)
    tax_id_gst = models.CharField('GSTIN / PAN', max_length=30, blank=True, help_text='GSTIN or Commercial Tax registration number')
    billing_address = models.TextField('Official Billing Address', blank=True)
    shipping_address = models.TextField('Delivery / Consignee Address', blank=True)
    city = models.CharField('City', max_length=100, blank=True)
    state = models.CharField('State / Territory', max_length=100, blank=True)
    credit_limit = models.DecimalField('Credit Limit (₹)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    credit_days = models.PositiveIntegerField('Credit Window (Days)', default=30)
    is_active = models.BooleanField('Active Client', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} [{self.get_customer_type_display()}] ({self.code})"

    def clean(self):
        if self.code:
            self.code = self.code.strip().upper()
        if self.credit_limit is not None and self.credit_limit < Decimal('0.00'):
            raise ValidationError("Credit limit cannot be negative.")


class RawMaterial(models.Model):
    """
    Raw chemicals, base polymers, active compounds, and ingredients consumed during manufacturing.
    """
    code = models.CharField('Material Code', max_length=30, unique=True, help_text='Unique identifier e.g. RM-101')
    name = models.CharField('Raw Material Name', max_length=150)
    description = models.TextField('Technical Specification', blank=True)
    category = models.CharField('Material Category', max_length=100, default='Industrial Chemical', blank=True)
    uom = models.ForeignKey(
        UnitOfMeasurement,
        on_delete=models.PROTECT,
        related_name='raw_materials',
        verbose_name='Inventory Unit'
    )
    standard_cost = models.DecimalField(
        'Standard Unit Cost (₹)',
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Standard inventory procurement price per primary UOM'
    )
    reorder_level = models.DecimalField(
        'Reorder Threshold',
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Inventory minimum threshold before initiating purchase orders'
    )
    preferred_supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='raw_materials',
        verbose_name='Approved Primary Supplier'
    )
    is_active = models.BooleanField('Active', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Raw Material'
        verbose_name_plural = 'Raw Materials'
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name} ({self.uom.code})"

    def clean(self):
        if self.code:
            self.code = self.code.strip().upper()
        if self.standard_cost is not None and self.standard_cost < Decimal('0.00'):
            raise ValidationError("Standard cost cannot be negative.")
        if self.reorder_level is not None and self.reorder_level < Decimal('0.00'):
            raise ValidationError("Reorder level cannot be negative.")


class PackagingMaterial(models.Model):
    """
    Primary and secondary packaging inventory (e.g. HDPE cans, closures, labels, corrugated shippers).
    """
    class MaterialType(models.TextChoices):
        BOTTLE = 'BOTTLE', 'Rigid Bottle / Can / Container'
        CAP = 'CAP', 'Cap / Closure / Dispenser Nozzle'
        LABEL = 'LABEL', 'Self-Adhesive Graphic Label'
        CARTON = 'CARTON', 'Corrugated Outer Shipper Carton'
        SEAL = 'SEAL', 'Induction / Tamper-Evident Seal'
        OTHER = 'OTHER', 'Other Packaging Accessory'

    code = models.CharField('Packaging Code', max_length=30, unique=True, help_text='Unique identifier e.g. PM-201')
    name = models.CharField('Packaging Item Name', max_length=150)
    material_type = models.CharField('Classification', max_length=20, choices=MaterialType.choices, default=MaterialType.BOTTLE)
    uom = models.ForeignKey(
        UnitOfMeasurement,
        on_delete=models.PROTECT,
        related_name='packaging_materials',
        verbose_name='Inventory Unit'
    )
    standard_cost = models.DecimalField(
        'Standard Unit Cost (₹)',
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Purchase cost per unit of packaging'
    )
    reorder_level = models.DecimalField(
        'Reorder Threshold',
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    preferred_supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='packaging_materials',
        verbose_name='Approved Primary Supplier'
    )
    is_active = models.BooleanField('Active', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Packaging Material'
        verbose_name_plural = 'Packaging Materials'
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name} [{self.get_material_type_display()}]"

    def clean(self):
        if self.code:
            self.code = self.code.strip().upper()
        if self.standard_cost is not None and self.standard_cost < Decimal('0.00'):
            raise ValidationError("Standard cost cannot be negative.")
        if self.reorder_level is not None and self.reorder_level < Decimal('0.00'):
            raise ValidationError("Reorder level cannot be negative.")


class Product(models.Model):
    """
    Finished goods formulations manufactured or distributed by the enterprise.
    """
    code = models.CharField('Product Code', max_length=30, unique=True, help_text='Unique identifier e.g. PRD-301')
    name = models.CharField('Finished Product Name', max_length=150)
    category = models.CharField('Product Family', max_length=100, default='Industrial Solution', blank=True)
    description = models.TextField('Product Description & Application', blank=True)
    base_uom = models.ForeignKey(
        UnitOfMeasurement,
        on_delete=models.PROTECT,
        related_name='products',
        verbose_name='Bulk Manufacturing Unit'
    )
    is_active = models.BooleanField('Active Product', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Finished Product'
        verbose_name_plural = 'Finished Products'
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        if self.code:
            self.code = self.code.strip().upper()


class ProductPackSize(models.Model):
    """
    Commercial SKUs and pack variants of a finished product (e.g. 500ml, 5L, 20L, 200L).
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='pack_sizes',
        verbose_name='Parent Product'
    )
    sku_code = models.CharField('SKU Code', max_length=40, unique=True, help_text='Unique commercial SKU identifier e.g. SKU-PRD301-5L')
    pack_name = models.CharField('Pack Size Description', max_length=100, help_text='e.g. 5 Litre Canister')
    pack_size_value = models.DecimalField(
        'Net Quantity in Pack',
        max_digits=10,
        decimal_places=2,
        help_text='Numeric quantity of bulk product contained (e.g. 5.00)'
    )
    uom = models.ForeignKey(
        UnitOfMeasurement,
        on_delete=models.PROTECT,
        related_name='pack_sizes',
        verbose_name='Pack Unit of Measure'
    )
    primary_packaging = models.ForeignKey(
        PackagingMaterial,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pack_sizes',
        verbose_name='Primary Container'
    )
    mrp = models.DecimalField(
        'Maximum Retail Price (₹)',
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Consumer list price inclusive of all taxes'
    )
    retailer_price = models.DecimalField(
        'Retailer B2B Price (₹)',
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Invoice price for direct retail stores'
    )
    distributor_price = models.DecimalField(
        'Distributor Wholesale Price (₹)',
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Wholesale tier invoice price for regional distributors'
    )
    barcode = models.CharField('EAN / UPC Barcode', max_length=50, blank=True)
    is_active = models.BooleanField('Active SKU', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pack Size SKU'
        verbose_name_plural = 'Pack Size SKUs'
        ordering = ['product', 'pack_size_value']

    def __str__(self):
        return f"{self.product.name} - {self.pack_name} ({self.sku_code})"

    def clean(self):
        if self.sku_code:
            self.sku_code = self.sku_code.strip().upper()
        if self.pack_size_value is not None and self.pack_size_value <= Decimal('0.00'):
            raise ValidationError("Pack size net quantity must be strictly greater than 0.")
        if self.mrp is not None and self.mrp < Decimal('0.00'):
            raise ValidationError("MRP cannot be negative.")
        if self.retailer_price is not None and self.retailer_price < Decimal('0.00'):
            raise ValidationError("Retailer price cannot be negative.")
        if self.distributor_price is not None and self.distributor_price < Decimal('0.00'):
            raise ValidationError("Distributor price cannot be negative.")


class BillOfMaterials(models.Model):
    """
    Standard Production Bill of Materials (BOM) specifying raw ingredients,
    packaging items, quantities, and expected yield percentage for a finished product batch.
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='boms',
        verbose_name='Finished Product'
    )
    bom_code = models.CharField('BOM Code', max_length=40, unique=True, help_text='Unique BOM identifier e.g. BOM-PRD301-V1')
    name = models.CharField('Formulation Title', max_length=150, help_text='e.g. Standard 100L Manufacturing Recipe')
    version = models.CharField('Revision / Version', max_length=20, default='v1.0')
    batch_size = models.DecimalField(
        'Standard Batch Size',
        max_digits=12,
        decimal_places=2,
        default=Decimal('100.00'),
        help_text='Base batch volume or weight to be produced'
    )
    output_uom = models.ForeignKey(
        UnitOfMeasurement,
        on_delete=models.PROTECT,
        related_name='bom_outputs',
        verbose_name='Batch Output Unit'
    )
    expected_yield_pct = models.DecimalField(
        'Expected Yield (%)',
        max_digits=5,
        decimal_places=2,
        default=Decimal('100.00'),
        help_text='Anticipated process recovery yield percentage (e.g. 98.50%)'
    )
    is_active_version = models.BooleanField(
        'Active Standard Revision',
        default=True,
        help_text='Check if this is the default BOM for work orders'
    )
    notes = models.TextField('Mixing & Processing Instructions', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Bill of Materials (BOM)'
        verbose_name_plural = 'Bills of Materials (BOMs)'
        ordering = ['product', '-version']

    def __str__(self):
        return f"{self.bom_code} - {self.name} for {self.product.name} ({self.version})"

    def clean(self):
        if self.bom_code:
            self.bom_code = self.bom_code.strip().upper()
        if self.batch_size is not None and self.batch_size <= Decimal('0.00'):
            raise ValidationError("Batch size must be strictly greater than 0.")
        if self.expected_yield_pct is not None:
            if self.expected_yield_pct <= Decimal('0.00') or self.expected_yield_pct > Decimal('100.00'):
                raise ValidationError("Expected yield percentage must be between 0.01% and 100.00%.")

    @property
    def expected_output_quantity(self):
        """Calculates expected net output volume after process loss: batch_size * (yield / 100)."""
        return (self.batch_size * (self.expected_yield_pct / Decimal('100.00'))).quantize(Decimal('0.01'))

    @property
    def total_estimated_cost(self):
        """Calculates total estimated material cost across all constituent ingredients."""
        total = Decimal('0.00')
        for item in self.items.all():
            total += item.line_cost
        return total.quantize(Decimal('0.01'))

    @property
    def cost_per_unit_output(self):
        """Calculates unit material cost based on expected yield."""
        expected_qty = self.expected_output_quantity
        if expected_qty > Decimal('0.00'):
            return (self.total_estimated_cost / expected_qty).quantize(Decimal('0.01'))
        return Decimal('0.00')


class BOMItem(models.Model):
    """
    Individual ingredient or packaging component within a Bill of Materials.
    Supports either a RawMaterial or a PackagingMaterial.
    """
    class ItemType(models.TextChoices):
        RAW_MATERIAL = 'RAW_MATERIAL', 'Raw Material'
        PACKAGING_MATERIAL = 'PACKAGING_MATERIAL', 'Packaging Material'

    bom = models.ForeignKey(
        BillOfMaterials,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Parent BOM'
    )
    item_type = models.CharField('Component Category', max_length=20, choices=ItemType.choices, default=ItemType.RAW_MATERIAL)
    raw_material = models.ForeignKey(
        RawMaterial,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='bom_items',
        verbose_name='Raw Material'
    )
    packaging_material = models.ForeignKey(
        PackagingMaterial,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='bom_items',
        verbose_name='Packaging Component'
    )
    quantity = models.DecimalField(
        'Required Quantity',
        max_digits=12,
        decimal_places=4,
        help_text='Quantity consumed per standard batch'
    )
    uom = models.ForeignKey(
        UnitOfMeasurement,
        on_delete=models.PROTECT,
        related_name='bom_items',
        verbose_name='Recipe Unit'
    )
    scrap_tolerance_pct = models.DecimalField(
        'Process Loss Allowance (%)',
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Additional scrap margin percentage expected during batch execution'
    )
    notes = models.CharField('Component Instructions / Sequence', max_length=200, blank=True)

    class Meta:
        verbose_name = 'BOM Component'
        verbose_name_plural = 'BOM Components'
        ordering = ['item_type', 'id']

    def __str__(self):
        return f"{self.ingredient_name}: {self.quantity} {self.uom.code}"

    def clean(self):
        if self.item_type == self.ItemType.RAW_MATERIAL:
            if not self.raw_material:
                raise ValidationError({'raw_material': "Please select a valid Raw Material."})
            if self.packaging_material:
                raise ValidationError({'packaging_material': "Cannot select a packaging material when component type is Raw Material."})
        elif self.item_type == self.ItemType.PACKAGING_MATERIAL:
            if not self.packaging_material:
                raise ValidationError({'packaging_material': "Please select a valid Packaging Material."})
            if self.raw_material:
                raise ValidationError({'raw_material': "Cannot select a raw material when component type is Packaging Material."})

        if self.quantity is not None and self.quantity <= Decimal('0.0000'):
            raise ValidationError({'quantity': "Ingredient quantity must be strictly greater than 0."})

        if self.scrap_tolerance_pct is not None and self.scrap_tolerance_pct < Decimal('0.00'):
            raise ValidationError({'scrap_tolerance_pct': "Scrap tolerance percentage cannot be negative."})

    @property
    def ingredient_name(self):
        if self.item_type == self.ItemType.RAW_MATERIAL and self.raw_material:
            return self.raw_material.name
        elif self.item_type == self.ItemType.PACKAGING_MATERIAL and self.packaging_material:
            return self.packaging_material.name
        return "Unknown Ingredient"

    @property
    def unit_cost(self):
        if self.item_type == self.ItemType.RAW_MATERIAL and self.raw_material:
            return self.raw_material.standard_cost
        elif self.item_type == self.ItemType.PACKAGING_MATERIAL and self.packaging_material:
            return self.packaging_material.standard_cost
        return Decimal('0.00')

    @property
    def line_cost(self):
        """Calculates line cost: quantity * unit_cost."""
        return (self.quantity * self.unit_cost).quantize(Decimal('0.01'))
