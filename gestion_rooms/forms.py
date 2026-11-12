from django import forms
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator

from account.models import ROLE_CLEANER, ROLE_RECEPTIONIST

from .models import CleaningTask, Invoice, Reservation, Room

User = get_user_model()


class DateInput(forms.DateInput):
    input_type = 'date'

    def __init__(self, **kw):
        super().__init__(format='%Y-%m-%d', **kw)


class DateTimeInput(forms.DateTimeInput):
    input_type = 'datetime-local'

    def __init__(self, **kw):
        super().__init__(format='%Y-%m-%dT%H:%M', **kw)


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ['hotel', 'number', 'category', 'capacity', 'price_per_night', 'status', 'description']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['price_per_night'].validators.append(MinValueValidator(0))
        from gestion_hotel.models import Hotel
        qs = Hotel.objects.filter(completed_step__gte=3)
        if user is not None:
            qs = qs.filter(owner=user)
        self.fields['hotel'].queryset = qs
        self.fields['hotel'].required = False
        self.fields['hotel'].empty_label = '— Aucun (chambre historique) —'


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ['reservation', 'amount', 'status', 'method']

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Reservation.objects.exclude(status__in=[Reservation.CANCELLED, Reservation.REFUSED])
        if user is not None and user.role == ROLE_RECEPTIONIST:
            qs = qs.filter(room__hotel_id=user.hotel_id)
        if not self.instance.pk:                      # une seule facture par réservation
            qs = qs.filter(invoice__isnull=True)
        self.fields['reservation'].queryset = qs
        self.fields['amount'].validators.append(MinValueValidator(0))

    def clean(self):
        data = super().clean()
        if data.get('status') == Invoice.PAID and not data.get('method'):
            self.add_error('method', 'Indiquez le mode de paiement pour une facture payée.')
        return data


class CleaningTaskForm(forms.ModelForm):
    class Meta:
        model = CleaningTask
        fields = ['room', 'assigned_to', 'scheduled_for', 'note']
        widgets = {'scheduled_for': DateTimeInput()}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None and user.role == ROLE_RECEPTIONIST:   # uniquement les chambres de SON hôtel
            self.fields['room'].queryset = Room.objects.filter(hotel_id=user.hotel_id)
        self.fields['assigned_to'].queryset = User.objects.filter(role=ROLE_CLEANER, is_active=True)
        self.fields['assigned_to'].required = False
        self.fields['assigned_to'].empty_label = 'Tous les agents'
