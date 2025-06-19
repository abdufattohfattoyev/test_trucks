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
                'placeholder': 'Select user'
            })

        # Apply styling to all fields
        for field in self.fields:
            if field != 'user':
                self.fields[field].widget.attrs.update({
                    'class': 'form-control',
                    'placeholder': f"Enter {self.fields[field].label.lower()}"
                })

        # Set required fields
        required_fields = ['po_id', 'make', 'model', 'year', 'horsepower', 'price', 'company', 'location']
        for field in required_fields:
            self.fields[field].required = True
            self.fields[field].widget.attrs['required'] = 'required'

        # Configure po_id field
        self.fields['po_id'].widget.attrs.update({
            'placeholder': 'Enter PO ID (e.g., PO-12345)'
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
        self.fields['image'].help_text = 'Optional - Recommended size: 800x600px'
        self.fields['seriya'].help_text = 'Optional - Vehicle serial number'
        self.fields['po_id'].help_text = 'Enter PO ID'
        self.fields['year'].help_text = 'Between 1900 and 2100'
        self.fields['horsepower'].help_text = 'Minimum 0 HP'
        self.fields['price'].help_text = 'In US dollars'
        self.fields['company'].help_text = 'Enter company name'
        self.fields['location'].help_text = 'Vehicle location'

    class Meta:
        model = Truck
        fields = [
            'user', 'po_id', 'make', 'model', 'year', 'horsepower', 'price', 'company',
            'location', 'description', 'image', 'seriya'
        ]
        labels = {
            'user': 'User',
            'po_id': 'PO ID',
            'make': 'Make',
            'model': 'Model',
            'year': 'Year',
            'horsepower': 'Horsepower (HP)',
            'price': 'Price ($)',
            'company': 'Company Name',
            'location': 'Location',
            'image': 'Vehicle Image',
            'description': 'Additional Notes',
            'seriya': 'Serial Number'
        }

    def clean_po_id(self):
        po_id = self.cleaned_data.get('po_id')
        if not po_id:
            raise ValidationError("PO ID is required.")
        if not po_id.startswith('PO-'):
            po_id = f"PO-{po_id}"
        if not re.match(r'^PO-\d+$', po_id):
            raise ValidationError("PO ID must start with 'PO-' followed by digits.")
        if Truck.objects.filter(po_id=po_id).exclude(id=self.instance.id if self.instance else None).exists():
            raise ValidationError("This PO ID is already taken.")
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
            self.add_error('year', 'Year must be between 1900 and 2100.')
        if horsepower is not None and horsepower < 0:
            self.add_error('horsepower', 'Horsepower cannot be negative.')
        if price is not None and price < 0:
            self.add_error('price', 'Price cannot be negative.')
        if make and len(make.strip()) < 2:
            self.add_error('make', 'Make must be at least 2 characters long.')
        if model and len(model.strip()) < 2:
            self.add_error('model', 'Model must be at least 2 characters long.')
        if company and len(company.strip()) < 2:
            self.add_error('company', 'Company name must be at least 2 characters long.')
        if location and len(location.strip()) < 2:
            self.add_error('location', 'Location must be at least 2 characters long.')
        if seriya and len(seriya.strip()) < 2:
            self.add_error('seriya', 'Serial number must be at least 2 characters long.')

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
            'hujjat': "Document or image (JPG, PNG, PDF, DOC, DOCX, multiple files allowed)",
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
                        raise ValidationError("Each file size must be less than 10MB!")
                    ext = file.name.split('.')[-1].lower()
                    if ext not in ['jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx']:
                        raise ValidationError("Only JPG, PNG, PDF, DOC, or DOCX files are supported!")
            else:
                if hujjatlar.size > 10 * 1024 * 1024:
                    raise ValidationError("File size must be less than 10MB!")
                ext = hujjatlar.name.split('.')[-1].lower()
                if ext not in ['jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx']:
                    raise ValidationError("Only JPG, PNG, PDF, DOC, or DOCX files are supported!")
        return hujjatlar