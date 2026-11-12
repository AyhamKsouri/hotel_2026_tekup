from django import forms
from django.core.exceptions import ValidationError

from gestion_rooms.forms import DateTimeInput

from .models import Event


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['title', 'description', 'start', 'end', 'location', 'capacity', 'price']
        widgets = {'start': DateTimeInput(), 'end': DateTimeInput(),
                   'description': forms.Textarea(attrs={'rows': 3})}

    def clean(self):
        data = super().clean()
        if data.get('start') and data.get('end') and data['end'] <= data['start']:
            raise ValidationError('La fin doit être après le début.')
        return data
