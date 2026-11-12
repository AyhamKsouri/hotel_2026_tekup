"""Formulaires de l'espace réceptionniste (un réceptionniste = un hôtel)."""
from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db.models import Q
from django.utils import timezone

from account.models import ROLE_CLIENT, ROLE_RECEPTIONIST, User as UserModel, validate_email_for_role

from .forms import DateInput
from .models import Invoice, Reservation, Room

User = get_user_model()


def hotel_rooms(user, include=None):
    """Chambres réservables par cet utilisateur : celles de SON hôtel pour un réceptionniste."""
    qs = Room.objects.exclude(status=Room.MAINTENANCE).select_related('hotel')
    if user.role == ROLE_RECEPTIONIST:
        qs = qs.filter(hotel_id=user.hotel_id)
    if include is not None:             # la chambre actuelle reste sélectionnable même en maintenance
        qs = Room.objects.filter(Q(pk__in=qs.values('pk')) | Q(pk=include.pk)).select_related('hotel')
    return qs.order_by('number')


class _StayDatesMixin:
    def _check_dates(self, data):
        ci, co = data.get('check_in'), data.get('check_out')
        if ci and co and co <= ci:
            self.add_error('check_out', "Le départ doit être après l'arrivée.")


class WalkInForm(_StayDatesMixin, forms.Form):
    """Réservation au comptoir pour un client existant (CIN / e-mail) ou un nouveau client."""
    EXISTING, NEW = 'existing', 'new'
    client_mode = forms.ChoiceField(label='Client', choices=[(EXISTING, 'Client existant'),
                                                             (NEW, 'Nouveau client')], initial=EXISTING)
    identifier = forms.CharField(label='CIN ou e-mail du client', required=False, max_length=254)
    cin = forms.CharField(label='CIN', required=False, max_length=8)
    nom = forms.CharField(required=False, max_length=100)
    prenom = forms.CharField(label='Prénom', required=False, max_length=100)
    telephone = forms.CharField(label='Téléphone', required=False, max_length=16)
    email = forms.EmailField(label='E-mail', required=False,
                             help_text='Doit se terminer par @booking.com (règle des comptes clients).')
    room = forms.ModelChoiceField(label='Chambre', queryset=Room.objects.none())
    check_in = forms.DateField(label='Arrivée', widget=DateInput())
    check_out = forms.DateField(label='Départ', widget=DateInput())
    amount = forms.DecimalField(label='Montant (TND)', required=False, max_digits=10, decimal_places=2,
                                validators=[MinValueValidator(0)],
                                help_text='Laisser vide : nuits × prix de la chambre.')
    check_in_now = forms.BooleanField(label="Le client arrive maintenant (check-in immédiat)", required=False)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['room'].queryset = hotel_rooms(user)
        self.client_obj = None

    def clean_check_in(self):
        d = self.cleaned_data['check_in']
        if d < timezone.localdate():
            raise ValidationError("La date d'arrivée ne peut pas être dans le passé.")
        return d

    def clean(self):
        data = super().clean()
        self._check_dates(data)
        if data.get('check_in_now') and data.get('check_in') and data['check_in'] != timezone.localdate():
            self.add_error('check_in_now', "Le check-in immédiat n'est possible que pour une arrivée aujourd'hui.")
        if data.get('client_mode') == self.EXISTING:
            ident = (data.get('identifier') or '').strip()
            if not ident:
                self.add_error('identifier', 'Indiquez le CIN ou l\'e-mail du client.')
            else:
                self.client_obj = User.objects.filter(
                    Q(cin=ident) | Q(email__iexact=ident), role=ROLE_CLIENT, is_active=True).first()
                if self.client_obj is None:
                    self.add_error('identifier', 'Aucun client actif avec ce CIN ou cet e-mail. '
                                                 'Choisissez « Nouveau client » pour le créer.')
        elif data.get('client_mode') == self.NEW:
            self._clean_new_client(data)
        return data

    def _clean_new_client(self, data):
        for f in ('cin', 'nom', 'prenom', 'telephone', 'email'):
            if not data.get(f):
                self.add_error(f, 'Champ obligatoire pour un nouveau client.')
        if self.errors:
            return
        candidate = UserModel(cin=data['cin'].strip(), nom=data['nom'].strip(), prenom=data['prenom'].strip(),
                              telephone=data['telephone'].strip(), email=data['email'].strip().lower(),
                              role=ROLE_CLIENT)
        try:
            candidate.full_clean(exclude=['password'])
        except ValidationError as e:
            for field, msgs in e.message_dict.items():
                self.add_error(field if field in self.fields else None, msgs)
            return
        candidate.set_unusable_password()   # le client choisira son mot de passe via « mot de passe oublié »
        self.new_client = candidate

    def get_client(self):
        """Client existant, ou nouveau client enregistré maintenant."""
        if self.client_obj is not None:
            return self.client_obj
        self.new_client.save()
        return self.new_client


class ReservationEditForm(_StayDatesMixin, forms.ModelForm):
    """Modification par la réception : chambre, dates et montant (la facture impayée suit)."""
    amount = forms.DecimalField(label='Montant (TND)', max_digits=10, decimal_places=2,
                                validators=[MinValueValidator(0)])

    class Meta:
        model = Reservation
        fields = ['room', 'check_in', 'check_out']
        widgets = {'check_in': DateInput(), 'check_out': DateInput()}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        res = self.instance
        self.fields['room'].queryset = hotel_rooms(user, include=res.room)
        self.fields['amount'].initial = res.total
        self.paid = Invoice.objects.filter(reservation=res, status=Invoice.PAID).exists()
        if self.paid:
            self.fields['amount'].disabled = True
            self.fields['amount'].help_text = 'Facture déjà payée : le montant ne peut plus changer.'
        else:
            self.fields['amount'].help_text = ('Montant actuel. Adaptez-le si la chambre ou la durée change ; '
                                               'la facture impayée sera mise à jour.')
        if res.status == Reservation.CHECKED_IN:   # client déjà dans la chambre : seul le départ peut bouger
            for f in ('room', 'check_in'):
                self.fields[f].disabled = True
            self.fields['check_out'].help_text = 'Séjour en cours : seule la date de départ est modifiable.'

    def clean(self):
        data = super().clean()
        self._check_dates(data)
        return data


class ClientProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['nom', 'prenom', 'telephone', 'email']

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        validate_email_for_role(email, ROLE_CLIENT)
        return email


class PaymentForm(forms.Form):
    method = forms.ChoiceField(label='Mode de paiement', choices=Invoice.METHOD_CHOICES, initial='cash')

