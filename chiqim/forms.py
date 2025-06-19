import bleach
from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from trucks.models import Truck
from xaridorlar.models import Xaridor
from .models import Chiqim, TolovTuri, BoshlangichTolov
import logging
from django.db import transaction

logger = logging.getLogger(__name__)

class ChiqimForm(forms.ModelForm):
    class Meta:
        model = Chiqim
        fields = ['truck', 'xaridor', 'narx', 'boshlangich_summa', 'hujjatlar', 'bo_lib_tolov_muddat', 'tolov_sana', 'izoh']
        widgets = {
            'tolov_sana': forms.DateInput(attrs={'type': 'date'}),
            'hujjatlar': forms.ClearableFileInput(),
        }

    def __init__(self, *args, user=None, instance=None, **kwargs):
        self.initial_instance = instance
        self.initial_truck = instance.truck if instance else None
        super().__init__(*args, instance=instance, **kwargs)
        if user:
            if not user.is_superuser:
                self.fields['truck'].queryset = Truck.objects.filter(user=user, sotilgan=False)
                self.fields['xaridor'].queryset = Xaridor.objects.filter(user=user)
            else:
                self.fields['truck'].queryset = Truck.objects.filter(sotilgan=False)
                self.fields['xaridor'].queryset = Xaridor.objects.all()
        else:
            self.fields['truck'].queryset = Truck.objects.none()
            self.fields['xaridor'].queryset = Xaridor.objects.none()

        if instance and instance.truck:
            self.fields['truck'].queryset = (self.fields['truck'].queryset | Truck.objects.filter(id=instance.truck.id)).distinct()
        self.fields['truck'].label_from_instance = lambda obj: f"{obj.make} {obj.model} {'(Series: ' + str(obj.seriya) + ')' if obj.seriya else ''}"
        logger.debug(f"Truck queryset: {self.fields['truck'].queryset.values('id', 'make', 'model', 'sotilgan')}")
        logger.debug(f"Customer queryset: {self.fields['xaridor'].queryset.values('id', 'ism_familiya', 'user__username')}")

        self.fields['tolov_sana'].required = True

    def save(self, commit=True):
        chiqim = super().save(commit=False)
        old_truck = self.initial_truck
        if commit:
            with transaction.atomic():
                if not self.initial_instance and chiqim.truck:
                    chiqim.truck.sotilgan = True
                    chiqim.truck.save()
                elif old_truck and old_truck != chiqim.truck:
                    old_truck.sotilgan = False
                    old_truck.save()
                    chiqim.truck.sotilgan = True
                    chiqim.truck.save()
                chiqim.save()
        return chiqim

    def clean(self):
        cleaned_data = super().clean()
        narx = cleaned_data.get('narx')
        boshlangich_summa = cleaned_data.get('boshlangich_summa', Decimal('0'))
        truck = cleaned_data.get('truck')
        xaridor = cleaned_data.get('xaridor')
        user = self.initial.get('user')

        if narx and boshlangich_summa > narx:
            raise forms.ValidationError("The initial payment amount cannot exceed the price!")
        if truck and truck.sotilgan and (not self.initial_instance or truck != self.initial_instance.truck):
            raise forms.ValidationError("This vehicle has already been sold!")
        if user and not user.is_superuser and xaridor and xaridor.user != user:
            raise forms.ValidationError("This customer does not belong to you!")
        return cleaned_data

class BoshlangichTolovForm(forms.ModelForm):
    class Meta:
        model = BoshlangichTolov
        fields = ['tolov_turi', 'summa', 'firma_nomi', 'bank', 'izoh', 'sana']
        widgets = {
            'sana': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_firma_nomi(self):
        firma_nomi = self.cleaned_data.get('firma_nomi')
        if firma_nomi:
            firma_nomi = bleach.clean(firma_nomi, tags=[], strip=True)
        return firma_nomi

    def clean_bank(self):
        bank = self.cleaned_data.get('bank')
        if bank:
            bank = bleach.clean(bank, tags=[], strip=True)
        return bank

    def clean_izoh(self):
        izoh = self.cleaned_data.get('izoh')
        if izoh:
            izoh = bleach.clean(izoh, tags=[], strip=True)
        return izoh

    def clean(self):
        cleaned_data = super().clean()
        summa = cleaned_data.get('summa')
        chiqim = self.initial.get('chiqim')
        if chiqim and summa:
            boshlangich_qoldiq = chiqim.get_boshlangich_qoldiq()
            if summa > boshlangich_qoldiq:
                raise forms.ValidationError(
                    f"The payment amount exceeds the initial remaining balance (${boshlangich_qoldiq:,.2f})!"
                )
        return cleaned_data

class TolovForm(forms.ModelForm):
    class Meta:
        model = TolovTuri
        fields = ['tolov_turi', 'summa', 'firma_nomi', 'bank', 'izoh', 'sana']
        widgets = {
            'sana': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_firma_nomi(self):
        firma_nomi = self.cleaned_data.get('firma_nomi')
        if firma_nomi:
            firma_nomi = bleach.clean(firma_nomi, tags=[], strip=True)
        return firma_nomi

    def clean_bank(self):
        bank = self.cleaned_data.get('bank')
        if bank:
            bank = bleach.clean(bank, tags=[], strip=True)
        return bank

    def clean_izoh(self):
        izoh = self.cleaned_data.get('izoh')
        if izoh:
            izoh = bleach.clean(izoh, tags=[], strip=True)
        return izoh

    def clean(self):
        cleaned_data = super().clean()
        summa = cleaned_data.get('summa')
        chiqim = self.initial.get('chiqim')

        if chiqim and summa:
            chiqim.refresh_from_db()  # Refresh the remaining balance
            remaining_balance = chiqim.qoldiq_summa
            if remaining_balance <= 0:
                raise ValidationError("The remaining balance is already paid, no additional payment is allowed!")
            if summa > remaining_balance:
                raise ValidationError(f"The payment amount exceeds the remaining balance (${remaining_balance:,.2f})!")
        return cleaned_data