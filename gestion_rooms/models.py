from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Room(models.Model):
    NORMAL, VIP, COUPLE, FAMILY = 'normal', 'vip', 'couple', 'family'
    CATEGORY_CHOICES = [(NORMAL, 'Normale'), (VIP, 'VIP'), (COUPLE, 'Couple'), (FAMILY, 'Familiale')]
    CAPACITY_CHOICES = [(2, '2 personnes'), (3, '3 personnes'), (4, '4 personnes')]

    AVAILABLE, OCCUPIED, TO_CLEAN, MAINTENANCE = 'available', 'occupied', 'to_clean', 'maintenance'
    STATUS_CHOICES = [
        (AVAILABLE, 'Disponible'), (OCCUPIED, 'Occupée'),
        (TO_CLEAN, 'À nettoyer'), (MAINTENANCE, 'Maintenance'),
    ]

    hotel = models.ForeignKey('gestion_hotel.Hotel', null=True, blank=True, on_delete=models.CASCADE,
                              related_name='rooms', verbose_name='hôtel')
    number = models.CharField('numéro', max_length=10)
    category = models.CharField('catégorie', max_length=10, choices=CATEGORY_CHOICES, default=NORMAL)
    capacity = models.PositiveSmallIntegerField('capacité', choices=CAPACITY_CHOICES, default=2)
    price_per_night = models.DecimalField('prix par nuit', max_digits=8, decimal_places=2)
    status = models.CharField('statut', max_length=12, choices=STATUS_CHOICES, default=AVAILABLE)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['number']
        constraints = [
            models.UniqueConstraint(fields=['hotel', 'number'], name='uniq_room_number_per_hotel'),
            # chambres historiques (sans hôtel) : le numéro reste unique
            models.UniqueConstraint(fields=['number'], condition=Q(hotel__isnull=True),
                                    name='uniq_room_number_no_hotel'),
        ]

    def __str__(self):
        base = f'Chambre {self.number} ({self.get_category_display()}, {self.capacity} pers.)'
        return f'{self.hotel.name} – {base}' if self.hotel_id else base

    def is_free_between(self, check_in, check_out, exclude_pk=None):
        qs = Reservation.objects.active().filter(
            room=self, check_in__lt=check_out, check_out__gt=check_in)
        if exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        return not qs.exists()


class Booking(models.Model):
    """Demande de réservation faite par un client dans un hôtel (peut couvrir plusieurs chambres).
    Chaque chambre réservée correspond à une `Reservation` (suivie par la réception)."""
    FAMILY, COUPLE, SINGLE, OTHER = 'family', 'couple', 'single', 'other'
    TYPE_CHOICES = [(FAMILY, 'Famille'), (COUPLE, 'Couple'), (SINGLE, 'Individuel'), (OTHER, 'Autre')]

    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookings')
    hotel = models.ForeignKey('gestion_hotel.Hotel', on_delete=models.PROTECT, related_name='bookings')
    full_name = models.CharField('nom complet', max_length=150)
    booking_type = models.CharField('type de réservation', max_length=10, choices=TYPE_CHOICES)
    persons = models.PositiveSmallIntegerField('nombre de personnes')
    children_ages = models.JSONField('âges des enfants', default=list, blank=True)
    check_in = models.DateField('arrivée')
    check_out = models.DateField('départ')
    extras = models.JSONField('accès / services', default=list, blank=True)
    total = models.DecimalField('total', max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Réservation hôtel #{self.pk} – {self.hotel.name}'


class ReservationQuerySet(models.QuerySet):
    def active(self):
        return self.exclude(status__in=[Reservation.CANCELLED, Reservation.CHECKED_OUT, Reservation.REFUSED])


class Reservation(models.Model):
    PENDING, CONFIRMED, CHECKED_IN, CHECKED_OUT, CANCELLED, REFUSED = (
        'pending', 'confirmed', 'checked_in', 'checked_out', 'cancelled', 'refused')
    STATUS_CHOICES = [
        (PENDING, 'Réclamée (en attente)'), (CONFIRMED, 'Confirmée'), (CHECKED_IN, 'Séjour en cours'),
        (CHECKED_OUT, 'Terminée'), (CANCELLED, 'Annulée'), (REFUSED, 'Refusée'),
    ]

    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                               related_name='reservations')
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name='reservations')
    check_in = models.DateField('arrivée')
    check_out = models.DateField('départ')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    booking = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.CASCADE,
                                related_name='reservations')
    # montant calculé par le formulaire client (personnes, enfants, accès) ; sinon nuits × prix chambre
    price_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    objects = ReservationQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Réservation #{self.pk} – {self.room.number} ({self.check_in} → {self.check_out})'

    @property
    def nights(self):
        return max((self.check_out - self.check_in).days, 0)

    @property
    def total(self):
        if self.price_override is not None:
            return self.price_override
        return Decimal(self.nights) * self.room.price_per_night

    def clean(self):
        if self.check_in and self.check_out:
            if self.check_out <= self.check_in:
                raise ValidationError('La date de départ doit être après la date d\'arrivée.')
            if self.room_id and self.status not in (self.CANCELLED, self.CHECKED_OUT, self.REFUSED) \
                    and not self.room.is_free_between(self.check_in, self.check_out, self.pk):
                raise ValidationError('Cette chambre est déjà réservée sur cette période.')


class Invoice(models.Model):
    UNPAID, PAID = 'unpaid', 'paid'
    STATUS_CHOICES = [(UNPAID, 'Impayée'), (PAID, 'Payée')]
    METHOD_CHOICES = [('cash', 'Espèces'), ('card', 'Carte bancaire'), ('transfer', 'Virement')]

    reservation = models.OneToOneField(Reservation, on_delete=models.CASCADE, related_name='invoice')
    amount = models.DecimalField('montant', max_digits=10, decimal_places=2)
    status = models.CharField('statut', max_length=8, choices=STATUS_CHOICES, default=UNPAID)
    method = models.CharField('mode de paiement', max_length=10, choices=METHOD_CHOICES, blank=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-issued_at']

    def __str__(self):
        return f'Facture #{self.pk} – {self.amount} TND'

    def save(self, *args, **kwargs):
        if self.status == self.PAID and not self.paid_at:
            self.paid_at = timezone.now()
        if self.status == self.UNPAID:
            self.paid_at = None
        super().save(*args, **kwargs)


class CleaningTaskQuerySet(models.QuerySet):
    def for_cleaner(self, user):
        """Tâches assignées à cet agent + tâches non assignées."""
        return self.filter(Q(assigned_to=user) | Q(assigned_to__isnull=True))


class CleaningTask(models.Model):
    PENDING, DONE = 'pending', 'done'
    STATUS_CHOICES = [(PENDING, 'À nettoyer'), (DONE, 'Nettoyée')]

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='cleaning_tasks')
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='cleaning_tasks', limit_choices_to={'role': 'cleaner'},
        verbose_name='agent assigné')
    scheduled_for = models.DateTimeField('heure de nettoyage', default=timezone.now)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default=PENDING)
    done_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)
    reminded = models.BooleanField(default=False)  # rappel « c'est l'heure » déjà envoyé

    objects = CleaningTaskQuerySet.as_manager()

    class Meta:
        ordering = ['scheduled_for']

    def __str__(self):
        return f'Nettoyage {self.room.number} – {self.scheduled_for:%d/%m %H:%M}'
