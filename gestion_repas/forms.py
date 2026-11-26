from django import forms
from django.core.validators import MinValueValidator
from django.utils import timezone

from gestion_hotel.hotel_forms import validate_image_size
from gestion_rooms.forms import DateInput

from .models import Menu, StockProduct


class MenuForm(forms.ModelForm):
    class Meta:
        model = Menu
        fields = ['date', 'name', 'category', 'description', 'image']
        widgets = {
            'date': DateInput(),
            'description': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Ingrédients, accompagnement, allergènes…'}),
            'image': forms.ClearableFileInput(attrs={'accept': 'image/*'}),
        }

    def __init__(self, *a, today_only=False, **kw):
        super().__init__(*a, **kw)
        self.fields['image'].validators.append(validate_image_size)
        if today_only:
            self.fields['date'].initial = timezone.localdate()
            self.fields['date'].disabled = True

    def clean_name(self):
        return self.cleaned_data['name'].strip()


class StockForm(forms.ModelForm):
    class Meta:
        model = StockProduct
        fields = ['name', 'category', 'quantity', 'unit', 'threshold', 'image']
        widgets = {
            'quantity': forms.NumberInput(attrs={'min': '0', 'step': '0.01', 'placeholder': '0'}),
            'threshold': forms.NumberInput(attrs={'min': '0', 'step': '0.01', 'placeholder': '5'}),
            'image': forms.ClearableFileInput(attrs={'accept': 'image/*'}),
        }

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        for f in ('quantity', 'threshold'):
            self.fields[f].validators.append(MinValueValidator(0))
        self.fields['image'].validators.append(validate_image_size)

    def clean_name(self):
        return self.cleaned_data['name'].strip()
