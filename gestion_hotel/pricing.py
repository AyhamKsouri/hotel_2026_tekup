"""Calcul du prix d'une réservation client.

Formule :  prix de la nuit (du type choisi, dans CET hôtel) × nombre de nuits
           × personnes payantes × (une ligne par chambre réservée)  + accès choisis.
Les enfants de moins de 11 ans sont gratuits : ils ne comptent pas dans les personnes payantes.
Cette logique est dupliquée côté navigateur (affichage en direct) ; le serveur recalcule toujours.
"""
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from .models import HotelService

FREE_UNDER_AGE = 11
TWO_PLACES = Decimal('0.01')


def money(v):
    return Decimal(v).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def chargeable_persons(persons, ages):
    return persons - sum(1 for a in ages if a < FREE_UNDER_AGE)


@dataclass
class Quote:
    nights: int
    chargeable: int
    room_lines: list = field(default_factory=list)   # [(catégorie, prix/nuit, montant)]
    extras: list = field(default_factory=list)       # [{'name','price','billing','amount'}]

    @property
    def rooms_total(self):
        return sum((amount for _, _, amount in self.room_lines), Decimal(0))

    @property
    def extras_total(self):
        return sum((Decimal(e['amount']) for e in self.extras), Decimal(0))

    @property
    def total(self):
        return money(self.rooms_total + self.extras_total)


def quote(hotel, room_types, nights, persons, ages, services):
    """room_types : liste de catégories (une par chambre) ; services : objets HotelService."""
    prices = {key: price for key, _label, _count, price, _cap in hotel.room_types()}
    chargeable = chargeable_persons(persons, ages)
    q = Quote(nights=nights, chargeable=chargeable)
    for cat in room_types:
        unit = prices[cat]
        q.room_lines.append((cat, unit, money(unit * nights * chargeable)))
    for s in services:
        mult = {HotelService.PER_STAY: 1, HotelService.PER_NIGHT: nights,
                HotelService.PER_PERSON: chargeable}[s.billing]
        q.extras.append({'name': s.name, 'price': str(s.price), 'billing': s.get_billing_display(),
                         'amount': str(money(s.price * mult))})
    return q
