"""Formulaire de réservation client + création des réservations."""
from collections import Counter

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from account.models import ROLE_RECEPTIONIST, User
from gestion_rooms import services as room_services
from gestion_rooms.forms import DateInput
from gestion_rooms.models import Booking, Reservation, Room

from . import pricing

MAX_ROOMS, MAX_PERSONS, MAX_CHILDREN, MAX_NIGHTS = 10, 50, 20, 60


class BookingForm(forms.Form):
    full_name = forms.CharField(label='Nom complet', max_length=150)
    booking_type = forms.ChoiceField(label='Type de réservation', choices=Booking.TYPE_CHOICES)
    check_in = forms.DateField(label='Arrivée', widget=DateInput())
    check_out = forms.DateField(label='Départ', widget=DateInput())
    persons = forms.IntegerField(label='Nombre de personnes (enfants inclus)', min_value=1, max_value=MAX_PERSONS)
    has_children = forms.BooleanField(label='Avez-vous des enfants ?', required=False)
    children_count = forms.IntegerField(label='Nombre d\'enfants', required=False, min_value=1,
                                        max_value=MAX_CHILDREN)
    rooms_count = forms.IntegerField(label='Nombre de chambres à réserver', min_value=1, max_value=MAX_ROOMS)

    def __init__(self, *args, hotel, **kwargs):
        super().__init__(*args, **kwargs)
        self.hotel = hotel
        self.allowed_types = {key: label for key, label, *_ in hotel.room_types()}
        self.capacity = {key: cap for key, _l, _n, _p, cap in hotel.room_types()}
        self.hotel_services = list(hotel.services.all())

    def clean_check_in(self):
        d = self.cleaned_data['check_in']
        if d < timezone.localdate():
            raise ValidationError('La date d\'arrivée ne peut pas être dans le passé.')
        return d

    def clean(self):
        data = super().clean()
        ci, co = data.get('check_in'), data.get('check_out')
        if ci and co:
            if co <= ci:
                self.add_error('check_out', 'Le départ doit être après l\'arrivée.')
            elif (co - ci).days > MAX_NIGHTS:
                self.add_error('check_out', f'Séjour limité à {MAX_NIGHTS} nuits.')
            else:
                data['nights'] = (co - ci).days

        # --- enfants et âges
        ages = []
        n_children = (data.get('children_count') or 0) if data.get('has_children') else 0
        if data.get('has_children') and not data.get('children_count'):
            self.add_error('children_count', 'Indiquez le nombre d\'enfants.')
        if n_children:
            raw = self.data.getlist('child_age')
            if len(raw) != n_children:
                self.add_error('children_count', 'Indiquez l\'âge de chaque enfant.')
            else:
                try:
                    ages = [int(a) for a in raw]
                    if any(a < 0 or a > 17 for a in ages):
                        raise ValueError
                except ValueError:
                    self.add_error('children_count', 'Âges invalides (de 0 à 17 ans).')
                    ages = []
        persons = data.get('persons')
        if persons and n_children and persons - n_children < 1:
            self.add_error('persons', 'Il faut au moins un adulte parmi les personnes.')
        data['ages'] = ages

        # --- type de chaque chambre
        n_rooms = data.get('rooms_count')
        types = self.data.getlist('room_type')
        if n_rooms:
            if len(types) != n_rooms or any(t not in self.allowed_types for t in types):
                self.add_error('rooms_count', 'Choisissez le type de chaque chambre.')
            else:
                data['room_types'] = types
                # les enfants de moins de FREE_UNDER_AGE ans partagent le lit des parents
                beds = sum(self.capacity[t] for t in types)
                guests = pricing.chargeable_persons(persons, ages) if persons else 0
                if guests > beds:
                    self.add_error('rooms_count', f'Ces chambres accueillent {beds} personne{"s" if beds > 1 else ""} '
                                                  f'au maximum : ajoutez une chambre ou choisissez une chambre plus grande.')

        # --- accès / services cochés (uniquement ceux de CET hôtel)
        wanted = set(self.data.getlist('services'))
        data['chosen_services'] = [s for s in self.hotel_services if str(s.pk) in wanted]
        return data

    def quote(self):
        d = self.cleaned_data
        return pricing.quote(self.hotel, d['room_types'], d['nights'], d['persons'],
                             d['ages'], d['chosen_services'])


@transaction.atomic
def create_booking(hotel, client, form):
    """Affecte des chambres libres, crée la demande + une réservation par chambre. Lève ValidationError."""
    d = form.cleaned_data
    ci, co = d['check_in'], d['check_out']
    q = form.quote()

    busy = Reservation.objects.active().filter(
        room__hotel=hotel, check_in__lt=co, check_out__gt=ci).values('room_id')
    pools = {}
    for cat, n in Counter(d['room_types']).items():
        free = list(Room.objects.select_for_update().filter(hotel=hotel, category=cat)
                    .exclude(status=Room.MAINTENANCE).exclude(pk__in=busy).order_by('number')[:n])
        if len(free) < n:
            label = form.allowed_types[cat].lower()
            raise ValidationError(
                f'Seulement {len(free)} chambre(s) {label} disponible(s) sur ces dates (vous en demandez {n}).')
        pools[cat] = free

    booking = Booking.objects.create(
        client=client, hotel=hotel, full_name=d['full_name'], booking_type=d['booking_type'],
        persons=d['persons'], children_ages=d['ages'], check_in=ci, check_out=co,
        extras=q.extras, total=q.total)
    for i, (cat, _unit, amount) in enumerate(q.room_lines):
        # les accès (piscine, restaurant…) sont portés par la 1re chambre pour que la somme des factures = total
        amount = amount + (q.extras_total if i == 0 else 0)
        Reservation.objects.create(client=client, room=pools[cat].pop(0), check_in=ci, check_out=co,
                                   booking=booking, price_override=pricing.money(amount))
    room_services.notify(
        [*User.objects.filter(role=ROLE_RECEPTIONIST, is_active=True, hotel=hotel), hotel.owner],
        f'Nouvelle réservation #{booking.pk} à {hotel.name} : {len(q.room_lines)} chambre(s), '
        f'{ci:%d/%m} → {co:%d/%m}, {booking.total} TND.')
    return booking
