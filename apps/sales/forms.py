from decimal import Decimal
from datetime import date, timedelta
from django import forms
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError

from apps.master_data.models import Customer, ProductPackSize, UnitOfMeasurement
from .models import SalesOrder, SalesOrderItem, Invoice, Dispatch, PaymentRecord


class SalesOrderForm(forms.ModelForm):
    class Meta:
        model = SalesOrder
        fields = [
            'customer',
            'order_date',
            'expected_delivery_date',
            'delivery_address',
            'delivery_city',
            'delivery_state',
            'contact_person',
            'contact_phone',
            'discount_amount',
            'notes',
        ]
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select select2-enable', 'id': 'id_customer_select'}),
            'order_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'expected_delivery_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'delivery_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Delivery destination address...'}),
            'delivery_city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Tiruchirappalli'}),
            'delivery_state': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Tamil Nadu'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Site contact person'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact phone number'}),
            'discount_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'value': '0.00'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Customer instructions or delivery terms...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = Customer.objects.filter(is_active=True).order_by('name')
        if not self.initial.get('order_date'):
            self.initial['order_date'] = date.today()
        if not self.initial.get('expected_delivery_date'):
            self.initial['expected_delivery_date'] = date.today() + timedelta(days=2)
        if not self.initial.get('delivery_state'):
            self.initial['delivery_state'] = 'Tamil Nadu'


class SalesOrderItemForm(forms.ModelForm):
    class Meta:
        model = SalesOrderItem
        fields = [
            'product_pack_size',
            'quantity',
            'uom',
            'unit_price',
            'notes',
        ]
        widgets = {
            'product_pack_size': forms.Select(attrs={'class': 'form-select item-sku-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control item-qty-input', 'step': '0.01', 'min': '0.01'}),
            'uom': forms.Select(attrs={'class': 'form-select item-uom-select'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control item-price-input', 'step': '0.01', 'min': '0.00'}),
            'notes': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional line note'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product_pack_size'].queryset = ProductPackSize.objects.filter(is_active=True).select_related('product', 'uom')
        self.fields['uom'].queryset = UnitOfMeasurement.objects.filter(is_active=True)

    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity')
        if qty is not None and qty <= Decimal('0.00'):
            raise ValidationError("Quantity must be greater than zero.")
        return qty

    def clean_unit_price(self):
        price = self.cleaned_data.get('unit_price')
        if price is not None and price < Decimal('0.00'):
            raise ValidationError("Unit price cannot be negative.")
        return price


SalesOrderItemFormSet = inlineformset_factory(
    SalesOrder,
    SalesOrderItem,
    form=SalesOrderItemForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True
)


class SalesOrderApprovalForm(forms.Form):
    ACTION_CHOICES = [
        ('APPROVE', 'Verify & Approve Order'),
        ('REJECT', 'Reject Order'),
    ]
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )
    rejection_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Specify mandatory reason if rejecting this order...'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        reason = cleaned_data.get('rejection_reason', '').strip()
        if action == 'REJECT' and not reason:
            self.add_error('rejection_reason', "A clear rejection reason is mandatory when rejecting a sales order.")
        return cleaned_data


class SalesDispatchForm(forms.Form):
    carrier_name = forms.CharField(
        max_length=100,
        initial='Sri Murugan Roadways',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Sri Murugan Roadways'})
    )
    vehicle_number = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. TN 45 AX 8810'})
    )
    lr_number = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. LR-2026-0045'})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Delivery instructions, driver contact, route...'})
    )


class PaymentRecordForm(forms.ModelForm):
    class Meta:
        model = PaymentRecord
        fields = [
            'amount',
            'payment_mode',
            'transaction_reference',
            'notes',
        ]
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'payment_mode': forms.Select(attrs={'class': 'form-select'}),
            'transaction_reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Bank UTR / Cheque / Transaction ID'}),
            'notes': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Received via NEFT to SBI'}),
        }

    def clean_amount(self):
        amt = self.cleaned_data.get('amount')
        if amt is not None and amt <= Decimal('0.00'):
            raise ValidationError("Payment amount must be strictly greater than zero.")
        return amt
