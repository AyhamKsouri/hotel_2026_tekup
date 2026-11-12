"""Formulaires de l'assistant « Créer mon hôtel » (3 étapes)."""
from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory

from .models import MAX_ROOMS_PER_TYPE, BookingPlan, Hotel, HotelService

MAX_IMAGE_MB = 5
COUNTRIES = ['Tunisie', 'Algérie', 'Maroc', 'Libye', 'Égypte', 'France', 'Italie', 'Espagne',
             'Allemagne', 'Turquie', 'Émirats arabes unis', 'Arabie saoudite', 'Qatar', 'Royaume-Uni']


def validate_image_size(f):
    if f and hasattr(f, 'size') and f.size > MAX_IMAGE_MB * 1024 * 1024:
        raise ValidationError(f'Image trop lourde (maximum {MAX_IMAGE_MB} Mo).')


# ------------------------------------------------------------------ étape 1
class HotelInfoForm(forms.ModelForm):
    class Meta:
        model = Hotel
        fields = ['name', 'phone', 'stars', 'country', 'city', 'address', 'description']
        widgets = {
            'stars': forms.Select(choices=[(n, '★' * n + f'  ({n})') for n in range(1, 6)]),
            'country': forms.TextInput(attrs={'list': 'countries', 'autocomplete': 'off'}),
            'phone': forms.TextInput(attrs={'placeholder': '+21671000000', 'inputmode': 'tel'}),
            'description': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Présentez votre hôtel : ambiance, emplacement, points forts…'}),
        }

    def clean_name(self):
        return self.cleaned_data['name'].strip()


# ------------------------------------------------------------------ étape 2
class HotelRoomsForm(forms.ModelForm):
    class Meta:
        model = Hotel
        fields = ['image_normal', 'image_vip', 'image_couple', 'image_family',
                  'count_normal', 'count_vip', 'count_couple', 'count_family']
        widgets = {
            'image_normal': forms.FileInput(attrs={'accept': 'image/*'}),
            'image_vip': forms.FileInput(attrs={'accept': 'image/*'}),
            'image_couple': forms.FileInput(attrs={'accept': 'image/*'}),
            'image_family': forms.FileInput(attrs={'accept': 'image/*'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('count_normal', 'count_vip', 'count_couple', 'count_family'):
            self.fields[name].widget = forms.NumberInput(
                attrs={'min': 0, 'max': MAX_ROOMS_PER_TYPE, 'data-count': '1'})
            self.fields[name].initial = 0
        for name in ('image_normal', 'image_vip', 'image_couple', 'image_family'):
            self.fields[name].validators.append(validate_image_size)

    def clean(self):
        data = super().clean()
        counts = {k: data.get(k) or 0 for k in
                  ('count_normal', 'count_vip', 'count_couple', 'count_family')}
        if sum(counts.values()) < 1:
            raise ValidationError('Indiquez au moins une chambre.')
        # une image est demandée pour chaque type de chambre utilisé
        for count_key, img_key, label in (('count_normal', 'image_normal', 'normale'),
                                          ('count_vip', 'image_vip', 'VIP'),
                                          ('count_couple', 'image_couple', 'couple'),
                                          ('count_family', 'image_family', 'familiale')):
            has_image = bool(data.get(img_key)) or bool(getattr(self.instance, img_key))
            if counts[count_key] > 0 and not has_image and img_key not in self.errors:
                self.add_error(img_key, f'Ajoutez une image de la chambre {label}.')
        return data


# ------------------------------------------------------------------ étape 3
class HotelPricingForm(forms.ModelForm):
    """Un prix par type de chambre réellement proposé (nombre > 0 à l'étape 2)."""
    FIELD_FOR = {'normal': 'price_normal', 'vip': 'price_vip',
                 'couple': 'price_couple', 'family': 'price_family'}

    class Meta:
        model = Hotel
        fields = ['price_normal', 'price_vip', 'price_couple', 'price_family']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        used = {key for key, *_ in self.instance.room_types()}
        for key, field_name in self.FIELD_FOR.items():
            if key not in used:
                del self.fields[field_name]
                continue
            f = self.fields[field_name]
            f.required = True
            f.widget = forms.NumberInput(attrs={'min': '0.01', 'step': '0.01', 'placeholder': '0.00'})
            f.validators.append(lambda v: _positive(v))


def _positive(v):
    if v is not None and v <= 0:
        raise ValidationError('Le prix doit être supérieur à 0.')


class UniqueNameFormSet(BaseInlineFormSet):
    """Refuse deux lignes portant le même nom (insensible à la casse)."""

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        seen = set()
        for form in self.forms:
            if self._should_delete_form(form) or not form.cleaned_data.get('name'):
                continue
            key = form.cleaned_data['name'].strip().lower()
            if key in seen:
                raise ValidationError(f'« {form.cleaned_data["name"]} » est présent deux fois.')
            seen.add(key)


class ServiceForm(forms.ModelForm):
    class Meta:
        model = HotelService
        fields = ['name', 'price', 'billing']
        widgets = {'name': forms.TextInput(attrs={'placeholder': 'Ex. Piscine'}),
                   'price': forms.NumberInput(attrs={'min': '0', 'step': '0.01', 'placeholder': '0.00'})}


class PlanForm(forms.ModelForm):
    class Meta:
        model = BookingPlan
        fields = ['name', 'description', 'supplement']
        widgets = {'name': forms.TextInput(attrs={'placeholder': 'Ex. Demi-pension'}),
                   'description': forms.TextInput(attrs={'placeholder': 'Ce que comprend la formule'}),
                   'supplement': forms.NumberInput(attrs={'min': '0', 'step': '0.01', 'placeholder': '0.00'})}


ServiceFormSet = inlineformset_factory(
    Hotel, HotelService, form=ServiceForm, formset=UniqueNameFormSet, extra=0, can_delete=True)

PlanFormSet = inlineformset_factory(
    Hotel, BookingPlan, form=PlanForm, formset=UniqueNameFormSet, extra=0, can_delete=True,
    min_num=1, validate_min=True)

SERVICE_PRESETS = ['Wi-Fi', 'Petit-déjeuner', 'Parking', 'Navette aéroport', 'Piscine', 'Spa',
                   'Salle de sport', 'Restaurant', 'Événements', 'Blanchisserie', 'Garde d\'enfants']
PLAN_PRESETS = [
    ('Logement seul', 'Chambre uniquement, sans repas'),
    ('Petit-déjeuner inclus', 'Chambre + petit-déjeuner'),
    ('Demi-pension', 'Chambre + petit-déjeuner + dîner'),
    ('Pension complète', 'Chambre + les trois repas'),
    ('All inclusive', 'Repas, boissons et activités inclus'),
]
