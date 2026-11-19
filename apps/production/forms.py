from decimal import Decimal
from datetime import date, timedelta
from django import forms
from django.forms import inlineformset_factory

from apps.master_data.models import BillOfMaterials, ProductPackSize
from .models import ProductionRun, ProductionMaterialConsumption


class ProductionRunCreateForm(forms.ModelForm):
    class Meta:
        model = ProductionRun
        fields = [
            'bill_of_materials',
            'product_pack_size',
            'planned_quantity',
            'batch_number',
            'manufacture_date',
            'expiry_date',
            'variance_alert_threshold_pct',
            'notes',
        ]
        widgets = {
            'bill_of_materials': forms.Select(attrs={'class': 'form-select select2-enable', 'id': 'id_bom_select'}),
            'product_pack_size': forms.Select(attrs={'class': 'form-select', 'id': 'id_pack_size_select'}),
            'planned_quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'batch_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. LOT-FG-MRK200-RUN01'}),
            'manufacture_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'variance_alert_threshold_pct': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.10', 'value': '3.00'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Optional production planning remarks...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['bill_of_materials'].queryset = BillOfMaterials.objects.filter(is_active_version=True).select_related('product')
        self.fields['product_pack_size'].queryset = ProductPackSize.objects.filter(is_active=True).select_related('product')

        if not self.initial.get('manufacture_date'):
            self.initial['manufacture_date'] = date.today()
        if not self.initial.get('expiry_date'):
            self.initial['expiry_date'] = date.today() + timedelta(days=90)
        if not self.initial.get('planned_quantity'):
            self.initial['planned_quantity'] = Decimal('200.00')


class ProductionRunExecuteForm(forms.ModelForm):
    """
    Form to record actual output yield and overhead costs (Labour, Gas/Power).
    """
    class Meta:
        model = ProductionRun
        fields = [
            'actual_output_quantity',
            'damaged_quantity',
            'labour_cost',
            'power_gas_cost',
            'other_overhead_cost',
            'notes',
        ]
        widgets = {
            'actual_output_quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'id': 'id_actual_output'}),
            'damaged_quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'labour_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '1200.00'}),
            'power_gas_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '600.00'}),
            'other_overhead_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class ProductionMaterialConsumptionItemForm(forms.ModelForm):
    class Meta:
        model = ProductionMaterialConsumption
        fields = [
            'actual_quantity',
            'damaged_quantity',
            'source_batch_number',
            'notes',
        ]
        widgets = {
            'actual_quantity': forms.NumberInput(attrs={'class': 'form-control form-control-sm text-end', 'step': '0.0001'}),
            'damaged_quantity': forms.NumberInput(attrs={'class': 'form-control form-control-sm text-end', 'step': '0.0001'}),
            'source_batch_number': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }


ProductionMaterialConsumptionFormSet = inlineformset_factory(
    ProductionRun,
    ProductionMaterialConsumption,
    form=ProductionMaterialConsumptionItemForm,
    extra=0,
    can_delete=False
)
