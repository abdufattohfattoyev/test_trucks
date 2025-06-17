from django import forms
from .models import Xarajat

class XarajatForm(forms.ModelForm):
    class Meta:
        model = Xarajat
        fields = ['truck', 'expense_type', 'amount', 'description', 'date', 'document']
        widgets = {
            'truck': forms.Select(attrs={'class': 'form-control'}),
            'expense_type': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'document': forms.FileInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'truck': 'Truck',
            'expense_type': 'Expense Type',
            'amount': 'Amount',
            'description': 'Description',
            'date': 'Date',
            'document': 'Document (Optional)',
        }

    def clean(self):
        cleaned_data = super().clean()
        amount = cleaned_data.get('amount')
        if amount is not None and amount < 0:
            self.add_error('amount', 'Amount cannot be negative.')
        return cleaned_data