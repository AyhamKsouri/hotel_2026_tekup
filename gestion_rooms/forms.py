from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from account.models import ROLE_CLEANER, ROLE_CLIENT, ROLE_RECEPTIONIST

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
        from gestion_hotel.models import Hotel
        qs = Hotel.objects.filter(completed_step__gte=3)
        if user is not None:
            qs = qs.filter(owner=user)
        self.fields['hotel'].queryset = qs
        self.fields['hotel'].required = False
        self.fields['hotel'].empty_label = '— Aucun (chambre historique) —'


class ReservationForm(forms.ModelForm):
    """Le client réserve pour lui-même ; le réceptionniste choisit aussi le client."""

    class Meta:
        model = Reservation
        fields = ['client', 'room', 'check_in', 'check_out']
        widgets = {'check_in': DateInput(), 'check_out': DateInput()}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        rooms = Room.objects.exclude(status=Room.MAINTENANCE)
        if user is not None and user.role == ROLE_RECEPTIONIST:
            rooms = rooms.filter(hotel_id=user.hotel_id)
        self.fields['room'].queryset = rooms
        if user is not None and user.role == ROLE_CLIENT:
            del self.fields['client']
        else:
            self.fields['client'].queryset = User.objects.filter(role=ROLE_CLIENT)

    def clean_check_in(self):
        d = self.cleaned_data['check_in']
        if not self.instance.pk and d < timezone.localdate():
            raise forms.ValidationError('La date d\'arrivée ne peut pas être dans le passé.')
        return d

    def _post_clean(self):
        if self.user is not None and self.user.role == ROLE_CLIENT:
            self.instance.client = self.user
        super()._post_clean()


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ['reservation', 'amount', 'status', 'method']

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None and user.role == ROLE_RECEPTIONIST:
            self.fields['reservation'].queryset = Reservation.objects.filter(room__hotel_id=user.hotel_id)

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_to'].queryset = User.objects.filter(role=ROLE_CLEANER, is_active=True)
        self.fields['assigned_to'].required = False
        self.fields['assigned_to'].empty_label = 'Tous les agents'
