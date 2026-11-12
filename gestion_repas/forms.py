from django import forms
from django.core.validators import MinValueValidator

from gestion_rooms.forms import DateInput

from .models import Menu, StockProduct


class MenuForm(forms.ModelForm):
    class Meta:
        model = Menu
        fields = ['date', 'name', 'category', 'description', 'price']
        widgets = {'date': DateInput(), 'description': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields['price'].validators.append(MinValueValidator(0))


class StockForm(forms.ModelForm):
    class Meta:
        model = StockProduct
        fields = ['name', 'category', 'quantity', 'unit', 'threshold']

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        for f in ('quantity', 'threshold'):
            self.fields[f].validators.append(MinValueValidator(0))
