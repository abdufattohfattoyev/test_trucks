from django import forms
from .models import Qarz, Payment
from trucks.models import Truck


class QarzForm(forms.ModelForm):
    borrower_name = forms.CharField(
        label="Borrower Name",
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    truck = forms.ModelChoiceField(
        queryset=Truck.objects.all(),
        label="Truck (Optional)",
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    payment_due_date = forms.DateField(
        label="Payment Due Date",
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    amount = forms.DecimalField(
        label="Loan Amount ($)",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    description = forms.CharField(
        label="Description",
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3})
    )
    is_paid = forms.BooleanField(
        label="Is Paid",
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = Qarz
        fields = ['borrower_name', 'truck', 'amount', 'payment_due_date', 'description', 'is_paid']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['truck'].queryset = Truck.objects.filter(user=user)


class PaymentForm(forms.ModelForm):
    amount = forms.DecimalField(
        label="Payment Amount ($)",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    payment_date = forms.DateField(
        label="Payment Date",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    description = forms.CharField(
        label="Description",
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3})
    )

    class Meta:
        model = Payment
        fields = ['amount', 'payment_date', 'description']