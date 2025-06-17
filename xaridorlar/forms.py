from django import forms
from .models import Xaridor, XaridorHujjat
from django.core.exceptions import ValidationError
from datetime import date

class MultiFileInput(forms.ClearableFileInput):
    """Custom widget supporting multiple file uploads."""
    allow_multiple_selected = True

    def __init__(self, attrs=None):
        if attrs is not None:
            attrs = attrs.copy()
            attrs['multiple'] = True
        else:
            attrs = {'multiple': True}
        super().__init__(attrs)

class XaridorForm(forms.ModelForm):
    class Meta:
        model = Xaridor
        fields = ['ism_familiya', 'telefon_raqam', 'email', 'hozirgi_balans', 'sana', 'izoh']
        widgets = {
            'ism_familiya': forms.TextInput(attrs={
                'class': 'form-control',
                'required': True,
                'placeholder': 'Name and Surname (e.g., Ali Valiyev)',
            }),
            'telefon_raqam': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+998001234567',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'example@domain.com',
            }),
            'hozirgi_balans': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '0.01',
                'readonly': True,
            }),
            'sana': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'required': True,
            }),
            'izoh': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': "Additional comments (optional)",
            }),
        }
        labels = {
            'ism_familiya': "Name and Surname",
            'telefon_raqam': "Phone Number (optional)",
            'email': "Email Address (optional)",
            'hozirgi_balans': "Current Balance",
            'sana': "Date",
            'izoh': "Description (optional)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['hozirgi_balans'].disabled = True
        if self.instance and self.instance.pk:
            self.instance.update_financials()
            self.fields['hozirgi_balans'].initial = self.instance.hozirgi_balans

    def clean_ism_familiya(self):
        ism_familiya = self.cleaned_data.get('ism_familiya')
        if not ism_familiya or len(ism_familiya.strip()) < 3:
            raise ValidationError("Name and surname must be at least 3 characters long!")
        return ism_familiya

    def clean_sana(self):
        sana = self.cleaned_data.get('sana')
        if not sana:
            raise ValidationError("Date is required!")
        return sana

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and Xaridor.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError("This email address is already in use!")
        return email

class XaridorHujjatForm(forms.ModelForm):
    class Meta:
        model = XaridorHujjat
        fields = ['hujjat']
        widgets = {
            'hujjat': MultiFileInput(attrs={
                'class': 'form-control',
                'accept': '.jpg,.jpeg,.png,application/pdf,.doc,.docx',
                'multiple': True,
                'id': 'hujjat-input',
            }),
        }
        labels = {
            'hujjat': "Document or Image (JPG, PNG, PDF, DOC, DOCX, multiple files supported)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['hujjat'].required = False