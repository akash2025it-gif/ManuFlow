from decimal import Decimal
from datetime import date, timedelta
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.master_data.models import Customer, ProductPackSize, UnitOfMeasurement


class SalesOrder(models.Model):
    """
    Sales Order created by Salesmen and verified/approved by Admin.
    Workflow: DRAFT -> SUBMITTED -> APPROVED / REJECTED -> INVOICED -> DISPATCHED.
    """
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft / In Creation'
        SUBMITTED = 'SUBMITTED', 'Submitted for Admin Approval'
        APPROVED = 'APPROVED', 'Approved by Admin'
        REJECTED = 'REJECTED', 'Rejected'
        INVOICED = 'INVOICED', 'Tax Invoiced'
        DISPATCHED = 'DISPATCHED', 'Dispatched & Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    order_number = models.CharField(
        'Order Number',
        max_length=40,
        unique=True,
        help_text='Unique identifier e.g. SO-2026-0001'
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='sales_orders',
        verbose_name='Customer'
    )
    salesman = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='sales_orders',
        verbose_name='Sales Representative'
    )
    order_date = models.DateField('Order Date', default=date.today)
    expected_delivery_date = models.DateField('Expected Delivery Date', null=True, blank=True)
    status = models.CharField('Order Status', max_length=25, choices=Status.choices, default=Status.DRAFT)

    # Delivery & Shipping Details
    delivery_address = models.TextField('Consignee / Delivery Address', blank=True)
    delivery_city = models.CharField('Delivery City', max_length=100, blank=True)
    delivery_state = models.CharField(
        'Delivery State',
        max_length=100,
        default='Tamil Nadu',
        help_text='State of delivery (determines intra-state CGST+SGST vs inter-state IGST)'
    )
    contact_person = models.CharField('Site Contact Person', max_length=100, blank=True)
    contact_phone = models.CharField('Site Phone', max_length=30, blank=True)

    # Tax & Commercial Valuation
    is_interstate = models.BooleanField(
        'Inter-State Sale',
        default=False,
        help_text='True if delivery is outside Tamil Nadu (applies 5% IGST instead of 2.5% CGST + 2.5% SGST)'
    )
    subtotal_amount = models.DecimalField(
        'Taxable Subtotal (₹)',
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Total selling price before GST'
    )
    discount_amount = models.DecimalField(
        'Discount (₹)',
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    cgst_amount = models.DecimalField(
        'CGST (2.5%) (₹)',
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    sgst_amount = models.DecimalField(
        'SGST (2.5%) (₹)',
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    igst_amount = models.DecimalField(
        'IGST (5.0%) (₹)',
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    total_tax_amount = models.DecimalField(
        'Total GST (₹)',
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    total_amount = models.DecimalField(
        'Grand Total (₹)',
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Inclusive of all GST taxes'
    )

    # Admin Verification & Audit
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales_orders_approved',
        verbose_name='Verified & Approved By'
    )
    approved_at = models.DateTimeField('Approval Timestamp', null=True, blank=True)
    rejection_reason = models.TextField('Rejection Reason / Notes', blank=True)

    notes = models.TextField('Order Instructions & Shipping Notes', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Sales Order'
        verbose_name_plural = 'Sales Orders'
        ordering = ['-order_date', '-created_at']

    def __str__(self):
        return f"{self.order_number} - {self.customer.name} ({self.get_status_display()})"

    def clean(self):
        if self.order_number:
            self.order_number = self.order_number.strip().upper()

    def get_absolute_url(self):
        return reverse('sales_order_detail', kwargs={'pk': self.pk})

    def update_totals(self):
        """
        Calculates and commits order financial totals:
        - Determines intra-state vs inter-state based on delivery_state (Tamil Nadu = Intra).
        - Computes 2.5% CGST + 2.5% SGST for Tamil Nadu sales.
        - Computes 5.0% IGST for inter-state sales.
        """
        # Determine intra vs inter-state
        state_str = (self.delivery_state or self.customer.state or 'Tamil Nadu').strip().lower()
        self.is_interstate = (state_str != 'tamil nadu' and state_str != 'tn')

        subtotal = Decimal('0.00')
        cgst_tot = Decimal('0.00')
        sgst_tot = Decimal('0.00')
        igst_tot = Decimal('0.00')

        for item in self.items.all():
            item_subtotal = (item.quantity * item.unit_price).quantize(Decimal('0.01'))
            item.subtotal = item_subtotal

            if self.is_interstate:
                item.cgst_rate_pct = Decimal('0.00')
                item.cgst_amount = Decimal('0.00')
                item.sgst_rate_pct = Decimal('0.00')
                item.sgst_amount = Decimal('0.00')
                item.igst_rate_pct = Decimal('5.00')
                item.igst_amount = (item_subtotal * Decimal('0.0500')).quantize(Decimal('0.01'))
                item.tax_amount = item.igst_amount
                igst_tot += item.igst_amount
            else:
                item.cgst_rate_pct = Decimal('2.50')
                item.cgst_amount = (item_subtotal * Decimal('0.0250')).quantize(Decimal('0.01'))
                item.sgst_rate_pct = Decimal('2.50')
                item.sgst_amount = (item_subtotal * Decimal('0.0250')).quantize(Decimal('0.01'))
                item.igst_rate_pct = Decimal('0.00')
                item.igst_amount = Decimal('0.00')
                item.tax_amount = item.cgst_amount + item.sgst_amount
                cgst_tot += item.cgst_amount
                sgst_tot += item.sgst_amount

            item.total_price = item_subtotal + item.tax_amount
            item.save(update_fields=[
                'subtotal', 'cgst_rate_pct', 'cgst_amount',
                'sgst_rate_pct', 'sgst_amount', 'igst_rate_pct',
                'igst_amount', 'tax_amount', 'total_price'
            ])
            subtotal += item_subtotal

        self.subtotal_amount = subtotal
        taxable = max(Decimal('0.00'), subtotal - self.discount_amount)

        if self.is_interstate:
            self.cgst_amount = Decimal('0.00')
            self.sgst_amount = Decimal('0.00')
            self.igst_amount = (taxable * Decimal('0.0500')).quantize(Decimal('0.01'))
            self.total_tax_amount = self.igst_amount
        else:
            self.cgst_amount = (taxable * Decimal('0.0250')).quantize(Decimal('0.01'))
            self.sgst_amount = (taxable * Decimal('0.0250')).quantize(Decimal('0.01'))
            self.igst_amount = Decimal('0.00')
            self.total_tax_amount = self.cgst_amount + self.sgst_amount

        self.total_amount = taxable + self.total_tax_amount
        self.save(update_fields=[
            'is_interstate', 'subtotal_amount', 'cgst_amount',
            'sgst_amount', 'igst_amount', 'total_tax_amount', 'total_amount'
        ])

    def get_stock_shortage(self):
        """
        Calculates total finished goods stock shortage across all line items.
        If sufficient inventory exists on hand, returns Decimal('0.00').
        If shortfall exists, returns the net positive shortage quantity.
        """
        from apps.inventory.models import StockItem
        total_short = Decimal('0.00')
        for line in self.items.all():
            stock_qs = StockItem.objects.filter(
                product_pack_size=line.product_pack_size,
                quantity_on_hand__gt=0
            )
            avail = sum(s.quantity_on_hand for s in stock_qs)
            if line.quantity > avail:
                total_short += (line.quantity - avail)
        return total_short


class SalesOrderItem(models.Model):
    """
    Individual finished goods SKU line item within a Sales Order.
    """
    sales_order = models.ForeignKey(
        SalesOrder,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Parent Sales Order'
    )
    product_pack_size = models.ForeignKey(
        ProductPackSize,
        on_delete=models.PROTECT,
        related_name='sales_order_items',
        verbose_name='Commercial Pack Size SKU'
    )
    quantity = models.DecimalField(
        'Ordered Quantity',
        max_digits=12,
        decimal_places=2,
        help_text='Quantity of retail packets / units'
    )
    uom = models.ForeignKey(
        UnitOfMeasurement,
        on_delete=models.PROTECT,
        related_name='+',
        verbose_name='Unit of Measure'
    )
    unit_price = models.DecimalField(
        'Selling Price (₹)',
        max_digits=12,
        decimal_places=2,
        help_text='Unit price before GST (e.g. ₹50.00 per benchmark)'
    )
    subtotal = models.DecimalField(
        'Taxable Subtotal (₹)',
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # GST Breakdown per item
    gst_rate_pct = models.DecimalField(
        'Applicable GST (%)',
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00')
    )
    cgst_rate_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('2.50'))
    cgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sgst_rate_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('2.50'))
    sgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    igst_rate_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    igst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_price = models.DecimalField(
        'Item Total Price (₹)',
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00')
    )

    dispatched_quantity = models.DecimalField(
        'Dispatched Qty',
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    notes = models.CharField('Line Notes', max_length=200, blank=True)

    class Meta:
        verbose_name = 'Sales Order Item'
        verbose_name_plural = 'Sales Order Items'
        ordering = ['id']

    def __str__(self):
        return f"{self.product_pack_size.pack_name} - {self.quantity} {self.uom.code} @ ₹{self.unit_price}"

    def clean(self):
        if self.quantity is not None and self.quantity <= Decimal('0.00'):
            raise ValidationError("Ordered quantity must be strictly greater than 0.")
        if self.unit_price is not None and self.unit_price < Decimal('0.00'):
            raise ValidationError("Unit price cannot be negative.")

    @property
    def item_name(self):
        return f"{self.product_pack_size.product.name} ({self.product_pack_size.pack_name})"

    @property
    def is_fully_dispatched(self):
        return self.dispatched_quantity >= self.quantity


class Invoice(models.Model):
    """
    Official GST Tax Invoice generated for an approved Sales Order.
    Includes full supplier & buyer snapshots, HSN codes, GST breakups, and payment readiness tracking.
    """
    class PaymentStatus(models.TextChoices):
        PENDING = 'PENDING', 'Payment Pending'
        PARTIAL = 'PARTIAL', 'Partially Paid'
        PAID = 'PAID', 'Fully Paid'

    invoice_number = models.CharField(
        'Tax Invoice Number',
        max_length=40,
        unique=True,
        help_text='e.g. INV-2026-0001'
    )
    sales_order = models.OneToOneField(
        SalesOrder,
        on_delete=models.PROTECT,
        related_name='invoice',
        verbose_name='Sales Order'
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='invoices',
        verbose_name='Customer'
    )
    invoice_date = models.DateField('Invoice Date', default=date.today)
    due_date = models.DateField('Payment Due Date', null=True, blank=True)

    # Supplier / Institutional Details (Seller Snapshot)
    company_name = models.CharField(
        'Supplier Name',
        max_length=150,
        default='NIT Trichy Snacks & Food Processing Centre'
    )
    company_gstin = models.CharField(
        'Supplier GSTIN (Demo / Placeholder)',
        max_length=60,
        default='33NITTRICHY1Z5 (Demo Placeholder)',
        help_text='Demo / simulated GSTIN for academic benchmarking. Not an officially registered commercial GSTIN.'
    )
    company_address = models.TextField(
        'Supplier Address',
        default='NIT Trichy Campus, Thuvakudi, Tiruchirappalli - 620015, Tamil Nadu'
    )
    company_state = models.CharField('Supplier State', max_length=100, default='Tamil Nadu')
    company_state_code = models.CharField('State Code', max_length=10, default='33')

    # Buyer / Customer Snapshot
    customer_name = models.CharField('Buyer Enterprise', max_length=150)
    customer_gstin = models.CharField('Buyer GSTIN', max_length=30, blank=True)
    billing_address = models.TextField('Official Billing Address')
    shipping_address = models.TextField('Delivery Destination Address')
    place_of_supply = models.CharField('Place of Supply (State)', max_length=100, default='Tamil Nadu')
    is_interstate = models.BooleanField('Inter-State Supply (IGST)', default=False)

    # Financial Breakdowns
    taxable_amount = models.DecimalField('Taxable Value (₹)', max_digits=14, decimal_places=2)
    cgst_rate_pct = models.DecimalField('CGST Rate (%)', max_digits=5, decimal_places=2, default=Decimal('2.50'))
    cgst_amount = models.DecimalField('CGST (₹)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sgst_rate_pct = models.DecimalField('SGST Rate (%)', max_digits=5, decimal_places=2, default=Decimal('2.50'))
    sgst_amount = models.DecimalField('SGST (₹)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    igst_rate_pct = models.DecimalField('IGST Rate (%)', max_digits=5, decimal_places=2, default=Decimal('0.00'))
    igst_amount = models.DecimalField('IGST (₹)', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_tax = models.DecimalField('Total GST (₹)', max_digits=12, decimal_places=2)
    grand_total = models.DecimalField('Invoice Total (₹)', max_digits=14, decimal_places=2)

    # Payment Readiness & Tracking
    payment_status = models.CharField(
        'Payment Status',
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING
    )
    amount_paid = models.DecimalField(
        'Amount Received (₹)',
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00')
    )
    payment_date = models.DateField('Last Payment Date', null=True, blank=True)
    payment_reference = models.CharField('Payment Bank Reference / UTR', max_length=100, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='invoices_created',
        verbose_name='Generated By'
    )
    notes = models.TextField('Invoice Terms & Declarations', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Tax Invoice'
        verbose_name_plural = 'Tax Invoices'
        ordering = ['-invoice_date', '-created_at']

    def __str__(self):
        return f"{self.invoice_number} - {self.customer_name} (₹{self.grand_total})"

    def clean(self):
        if self.invoice_number:
            self.invoice_number = self.invoice_number.strip().upper()

    def get_absolute_url(self):
        return reverse('invoice_detail', kwargs={'pk': self.pk})

    @property
    def balance_due(self):
        return max(Decimal('0.00'), self.grand_total - self.amount_paid)

    def update_payment_status(self):
        """Updates payment status based on total payments recorded."""
        total_p = sum(p.amount for p in self.payments.all())
        self.amount_paid = total_p
        if total_p >= self.grand_total:
            self.payment_status = self.PaymentStatus.PAID
        elif total_p > Decimal('0.00'):
            self.payment_status = self.PaymentStatus.PARTIAL
        else:
            self.payment_status = self.PaymentStatus.PENDING
        self.save(update_fields=['amount_paid', 'payment_status', 'updated_at'])


class Dispatch(models.Model):
    """
    Material Delivery Challan / Dispatch Note.
    Triggers finished goods inventory reduction in StockLedgerEntry.
    """
    class Status(models.TextChoices):
        PREPARED = 'PREPARED', 'Prepared in Warehouse'
        DISPATCHED = 'DISPATCHED', 'Dispatched / In Transit'
        DELIVERED = 'DELIVERED', 'Delivered & Consignee Acknowledged'

    dispatch_number = models.CharField(
        'Dispatch Ref Number',
        max_length=40,
        unique=True,
        help_text='e.g. DSP-2026-0001'
    )
    sales_order = models.ForeignKey(
        SalesOrder,
        on_delete=models.PROTECT,
        related_name='dispatches',
        verbose_name='Sales Order'
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dispatches',
        verbose_name='Linked Tax Invoice'
    )
    dispatch_date = models.DateField('Dispatch Date', default=date.today)
    carrier_name = models.CharField('Logistics / Transporter', max_length=100, default='Sri Murugan Roadways')
    vehicle_number = models.CharField('Truck / Vehicle Number', max_length=30, blank=True, help_text='e.g. TN 45 AX 8810')
    lr_number = models.CharField('LR / Waybill Number', max_length=50, blank=True)
    status = models.CharField('Dispatch Status', max_length=20, choices=Status.choices, default=Status.DISPATCHED)

    # Duplicate stock deduction prevention
    is_posted = models.BooleanField(
        'Stock Deducted from Ledger',
        default=False,
        help_text='Flag indicating stock deduction has been executed in the stock ledger'
    )
    posted_at = models.DateTimeField('Posting Timestamp', null=True, blank=True)
    dispatched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='dispatches_handled',
        verbose_name='Dispatched By'
    )
    notes = models.TextField('Transport & Dispatch Notes', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Dispatch Order'
        verbose_name_plural = 'Dispatch Orders'
        ordering = ['-dispatch_date', '-created_at']

    def __str__(self):
        return f"{self.dispatch_number} for {self.sales_order.order_number}"

    def clean(self):
        if self.dispatch_number:
            self.dispatch_number = self.dispatch_number.strip().upper()


class PaymentRecord(models.Model):
    """
    Payment receipt recorded against an Invoice for complete Order-to-Audit reconciliation.
    """
    class Mode(models.TextChoices):
        UPI = 'UPI', 'UPI / QR Direct Payment'
        CASH = 'CASH', 'Cash Counter Receipt'
        NEFT = 'NEFT', 'NEFT Bank Transfer'
        RTGS = 'RTGS', 'RTGS Bank Transfer'
        CHEQUE = 'CHEQUE', 'Cheque / Demand Draft'
        NEFT_RTGS = 'NEFT_RTGS', 'NEFT / RTGS Bank Transfer'
        NET_BANKING = 'NET_BANKING', 'Internet Banking'

    payment_number = models.CharField('Payment Voucher #', max_length=40, unique=True)
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='payments',
        verbose_name='Invoice'
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='payments',
        verbose_name='Customer'
    )
    payment_date = models.DateField('Payment Date', default=date.today)
    amount = models.DecimalField('Amount Received (₹)', max_digits=12, decimal_places=2)
    payment_mode = models.CharField('Payment Mode', max_length=25, choices=Mode.choices, default=Mode.NEFT_RTGS)
    transaction_reference = models.CharField('Bank UTR / Cheque #', max_length=100, blank=True)
    notes = models.CharField('Remittance Remarks', max_length=200, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='payments_recorded',
        verbose_name='Recorded By'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Payment Record'
        verbose_name_plural = 'Payment Records'
        ordering = ['-payment_date', '-created_at']

    def __str__(self):
        return f"{self.payment_number}: ₹{self.amount} for {self.invoice.invoice_number}"

    def clean(self):
        if self.amount is not None and self.amount <= Decimal('0.00'):
            raise ValidationError("Payment amount must be strictly greater than zero.")
