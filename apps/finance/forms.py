from decimal import Decimal
from datetime import date
from django import forms
from django.core.exceptions import ValidationError

from apps.master_data.models import Customer
from apps.inventory.models import ItemType, MovementType
from apps.sales.models import Invoice, PaymentRecord


class FinancePaymentForm(forms.Form):
    """
    Form to record a payment against an outstanding invoice.
    Reuses the existing PaymentRecord model and payment services in apps.sales.
    """
    invoice = forms.ModelChoiceField(
        queryset=Invoice.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select select2-enable', 'id': 'id_invoice_select'}),
        help_text="Select an approved invoice with an outstanding balance."
    )
    payment_date = forms.DateField(
        initial=date.today,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01', 'placeholder': '0.00'})
    )
    payment_mode = forms.ChoiceField(
        choices=PaymentRecord.Mode.choices,
        initial=PaymentRecord.Mode.UPI,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    transaction_reference = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Bank UTR / Cheque No / UPI Ref'})
    )
    notes = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Remarks / Bank branch details'})
    )

    def __init__(self, *args, invoice_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Invoices that are NOT fully paid (or include the specific invoice_id if passed)
        unpaid_invoices = Invoice.objects.exclude(
            payment_status=Invoice.PaymentStatus.PAID
        ).select_related('customer')

        if invoice_id:
            specific_qs = Invoice.objects.filter(pk=invoice_id).select_related('customer')
            self.fields['invoice'].queryset = (unpaid_invoices | specific_qs).distinct().order_by('-invoice_date')
            self.fields['invoice'].initial = invoice_id
        else:
            self.fields['invoice'].queryset = unpaid_invoices.order_by('-invoice_date')

    def clean_amount(self):
        amt = self.cleaned_data.get('amount')
        if amt is not None and amt <= Decimal('0.00'):
            raise ValidationError("Payment amount must be strictly greater than zero.")
        return amt

    def clean(self):
        cleaned_data = super().clean()
        invoice = cleaned_data.get('invoice')
        amount = cleaned_data.get('amount')

        if invoice and amount:
            if invoice.payment_status == Invoice.PaymentStatus.PAID:
                raise ValidationError(f"Invoice {invoice.invoice_number} is already fully settled (PAID). No further payments can be accepted.")
            if amount > invoice.balance_due:
                raise ValidationError(
                    f"Payment amount of ₹{amount:,.2f} exceeds the invoice remaining balance due of ₹{invoice.balance_due:,.2f}."
                )
        return cleaned_data


class SalesRegisterFilterForm(forms.Form):
    STATE_CHOICES = [
        ('', 'All Invoices (Intra & Inter)'),
        ('INTRA', 'Tamil Nadu Intra-State (2.5% CGST + 2.5% SGST)'),
        ('INTER', 'Inter-State (5% IGST)'),
    ]

    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    state_filter = forms.ChoiceField(
        choices=STATE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.filter(is_active=True).order_by('name'),
        required=False,
        empty_label="All Customers",
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class MonthlyGSTFilterForm(forms.Form):
    year = forms.IntegerField(
        min_value=2020,
        max_value=2050,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'YYYY'})
    )


class StockFilterForm(forms.Form):
    CATEGORY_CHOICES = [
        ('', 'All Stock Categories'),
        (ItemType.RAW_MATERIAL, 'Raw Materials'),
        (ItemType.PACKAGING_MATERIAL, 'Packaging Materials'),
        (ItemType.FINISHED_GOODS, 'Finished Goods'),
    ]
    category = forms.ChoiceField(
        choices=CATEGORY_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class StockLedgerFilterForm(forms.Form):
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    movement_type = forms.ChoiceField(
        choices=[('', 'All Movement Types')] + list(MovementType.choices),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    item_type = forms.ChoiceField(
        choices=[('', 'All Item Types')] + list(ItemType.choices),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class DateRangeFilterForm(forms.Form):
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
