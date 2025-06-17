import re
from django import forms
from django.core.exceptions import ValidationError
from .models import Truck, TruckHujjat
from django.contrib.auth.models import User

class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

    def __init__(self, attrs=None):
        if attrs is not None:
            attrs = attrs.copy()
            attrs['multiple'] = True
        else:
            attrs = {'multiple': True}
        super().__init__(attrs)

class TruckForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.is_edit = kwargs.get('instance', None) is not None

        # Configure user field
        if user and not user.is_superuser:
            self.fields['user'].widget = forms.HiddenInput()
            self.fields['user'].required = False
        else:
            self.fields['user'].queryset = User.objects.all()
            self.fields['user'].widget.attrs.update({
                'class': 'form-control',
                'placeholder': 'Foydalanuvchi tanlang'
            })

        # Apply styling to all fields
        for field in self.fields:
            if field != 'user':
                self.fields[field].widget.attrs.update({
                    'class': 'form-control',
                    'placeholder': f"{self.fields[field].label.lower()} kiriting"
                })

        # Set required fields
        required_fields = ['po_id', 'make', 'model', 'year', 'horsepower', 'price', 'company', 'location']
        for field in required_fields:
            self.fields[field].required = True
            self.fields[field].widget.attrs['required'] = 'required'

        # Configure po_id field
        self.fields['po_id'].widget.attrs.update({
            'placeholder': 'PO ID kiriting (masalan, PO-12345)'
        })

        # Additional field attributes
        self.fields['year'].widget.attrs.update({'min': 1900, 'max': 2100})
        self.fields['horsepower'].widget.attrs.update({'min': 0})
        self.fields['price'].widget.attrs.update({'step': '0.01'})
        self.fields['seriya'].widget.attrs.update({'maxlength': 50})
        self.fields['description'].widget.attrs.update({
            'rows': 3,
            'style': 'resize: vertical;'
        })
        self.fields['image'].widget.attrs.update({
            'class': 'form-control file-upload',
            'accept': 'image/*'
        })

        # Help texts
        self.fields['image'].help_text = 'Ixtiyoriy - Tavsiya etilgan olcham: 800x600px'
        self.fields['seriya'].help_text = 'Ixtiyoriy - Mashina seriya raqami'
        self.fields['po_id'].help_text = 'PO ID kiriting'
        self.fields['year'].help_text = '1900 va 2100 oraligida'
        self.fields['horsepower'].help_text = 'Minimal 0 HP'
        self.fields['price'].help_text = 'AQSh dollarida'
        self.fields['company'].help_text = 'Kompaniya nomini kiriting'
        self.fields['location'].help_text = 'Mashina joylashuvi'

    class Meta:
        model = Truck
        fields = [
            'user', 'po_id', 'make', 'model', 'year', 'horsepower', 'price', 'company',
            'location', 'description', 'image', 'seriya'
        ]
        labels = {
            'user': 'Foydalanuvchi',
            'po_id': 'PO ID',
            'make': 'Marka',
            'model': 'Model',
            'year': 'Yil',
            'horsepower': 'Ot kuchi (HP)',
            'price': 'Narx ($)',
            'company': 'Kompaniya nomi',
            'location': 'Joylashuv',
            'image': 'Mashina rasmi',
            'description': 'Qoshimcha izohlar',
            'seriya': 'Seriya raqami'
        }

    def clean_po_id(self):
        po_id = self.cleaned_data.get('po_id')
        if not po_id:
            raise ValidationError("PO ID kiritilishi shart.")
        if not po_id.startswith('PO-'):
            po_id = f"PO-{po_id}"
        if not re.match(r'^PO-\d+$', po_id):
            raise ValidationError("PO ID 'PO-' bilan boshlanib, raqamlar bilan davom etishi kerak.")
        if Truck.objects.filter(po_id=po_id).exclude(id=self.instance.id if self.instance else None).exists():
            raise ValidationError("Bu PO ID allaqachon band qilingan.")
        return po_id

    def clean(self):
        cleaned_data = super().clean()
        year = cleaned_data.get('year')
        horsepower = cleaned_data.get('horsepower')
        price = cleaned_data.get('price')
        make = cleaned_data.get('make')
        model = cleaned_data.get('model')
        company = cleaned_data.get('company')
        location = cleaned_data.get('location')
        seriya = cleaned_data.get('seriya')

        if year and (year < 1900 or year > 2100):
            self.add_error('year', 'Yil 1900 va 2100 oralig\'ida bo\'lishi kerak.')
        if horsepower is not None and horsepower < 0:
            self.add_error('horsepower', 'Ot kuchi manfiy bo\'lishi mumkin emas.')
        if price is not None and price < 0:
            self.add_error('price', 'Narx manfiy bo\'lishi mumkin emas.')
        if make and len(make.strip()) < 2:
            self.add_error('make', 'Marka kamida 2 ta belgidan iborat bo\'lishi kerak.')
        if model and len(model.strip()) < 2:
            self.add_error('model', 'Model kamida 2 ta belgidan iborat bo\'lishi kerak.')
        if company and len(company.strip()) < 2:
            self.add_error('company', 'Kompaniya nomi kamida 2 ta belgidan iborat bo\'lishi kerak.')
        if location and len(location.strip()) < 2:
            self.add_error('location', 'Joylashuv kamida 2 ta belgidan iborat bo\'lishi kerak.')
        if seriya and len(seriya.strip()) < 2:
            self.add_error('seriya', 'Seriya raqami kamida 2 ta belgidan iborat bo\'lishi kerak.')

        return cleaned_data

class TruckHujjatForm(forms.ModelForm):
    class Meta:
        model = TruckHujjat
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
            'hujjat': "Hujjat yoki rasm (JPG, PNG, PDF, DOC, DOCX, bir nechta fayl ruxsat etiladi)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['hujjat'].required = False

    def clean_hujjat(self):
        hujjatlar = self.cleaned_data.get('hujjat')
        if hujjatlar:
            if isinstance(hujjatlar, list):
                for file in hujjatlar:
                    if file.size > 10 * 1024 * 1024:
                        raise ValidationError("Har bir fayl hajmi 10MB dan kichik bo'lishi kerak!")
                    ext = file.name.split('.')[-1].lower()
                    if ext not in ['jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx']:
                        raise ValidationError("Faqat JPG, PNG, PDF, DOC yoki DOCX fayllari qo'llab-quvvatlanadi!")
            else:
                if hujjatlar.size > 10 * 1024 * 1024:
                    raise ValidationError("Fayl hajmi 10MB dan kichik bo'lishi kerak!")
                ext = hujjatlar.name.split('.')[-1].lower()
                if ext not in ['jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx']:
                    raise ValidationError("Faqat JPG, PNG, PDF, DOC yoki DOCX fayllari qo'llab-quvvatlanadi!")
        return hujjatlar