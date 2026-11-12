from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import (ROLE_ADMIN, ROLE_CHOICES, ROLE_CLIENT, ROLE_RECEPTIONIST, cin_validator,
                     validate_email_for_role)

User = get_user_model()


class PasswordPairMixin(forms.Form):
    password1 = forms.CharField(label='Mot de passe', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirmer le mot de passe', widget=forms.PasswordInput)

    def clean(self):
        data = super().clean()
        p1, p2 = data.get('password1'), data.get('password2')
        if p1 and p2:
            if p1 != p2:
                self.add_error('password2', 'Les deux mots de passe ne correspondent pas.')
            else:
                try:
                    validate_password(p1, getattr(self, 'instance', None))
                except ValidationError as e:
                    self.add_error('password1', e)
        return data


class SignupForm(PasswordPairMixin, forms.ModelForm):
    role = forms.ChoiceField(label='Type de compte', choices=ROLE_CHOICES, initial=ROLE_CLIENT)

    class Meta:
        model = User
        fields = ['cin', 'nom', 'prenom', 'telephone', 'email', 'role']
        labels = {'email': 'E-mail'}
        help_texts = {
            'email': 'Client : @booking.com · Employé : @service.com · Admin : @admin.com',
        }

    field_order = ['cin', 'nom', 'prenom', 'telephone', 'email', 'role', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not settings.ALLOW_STAFF_SIGNUP:
            self.fields['role'].choices = [(ROLE_CLIENT, 'Client')]

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()

    def clean(self):
        data = super().clean()
        email, role = data.get('email'), data.get('role')
        if email and role:
            try:
                validate_email_for_role(email, role)
            except ValidationError as e:
                self.add_error('email', e)
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    identifier = forms.CharField(label='E-mail ou CIN')
    password = forms.CharField(label='Mot de passe', widget=forms.PasswordInput)


class ResetStep1Form(forms.Form):
    cin = forms.CharField(label='CIN', validators=[cin_validator],
                          widget=forms.TextInput(attrs={'inputmode': 'numeric', 'maxlength': '8'}))
    email = forms.EmailField(label='E-mail')


class ResetStep2Form(forms.Form):
    code = forms.RegexField(r'^\d{6}$', label='Code à 6 chiffres', max_length=6,
                            error_messages={'invalid': 'Le code contient exactement 6 chiffres.'},
                            widget=forms.TextInput(attrs={
                                'inputmode': 'numeric', 'autocomplete': 'one-time-code',
                                'maxlength': '6', 'pattern': '[0-9]{6}', 'autofocus': True,
                                'class': 'otp-input'}))


class ResetStep3Form(PasswordPairMixin):
    pass


class UserAdminForm(forms.ModelForm):
    """Création / modification d'un utilisateur par l'administrateur."""
    password = forms.CharField(
        label='Mot de passe', widget=forms.PasswordInput(render_value=False), required=False,
        help_text='Laisser vide pour ne pas le changer (obligatoire à la création).')

    class Meta:
        model = User
        fields = ['cin', 'nom', 'prenom', 'telephone', 'email', 'role', 'hotel', 'is_active']

    def __init__(self, *args, admin=None, **kwargs):
        super().__init__(*args, **kwargs)
        from django.db.models import Q
        from gestion_hotel.models import Hotel
        # l'admin n'affecte un réceptionniste qu'à l'un de SES hôtels terminés
        qs = Hotel.objects.filter(completed_step__gte=3)
        if admin is not None:
            keep = Q(owner=admin) | (Q(pk=self.instance.hotel_id) if self.instance.hotel_id else Q())
            qs = qs.filter(keep)
        self.fields['hotel'].queryset = qs
        self.fields['hotel'].required = False
        self.fields['hotel'].empty_label = '— Aucun —'
        self.fields['hotel'].label = 'Hôtel où travaille le réceptionniste'
        # seul un super-administrateur peut créer ou nommer un administrateur
        self.admin = admin
        if admin is not None and not admin.is_superuser and self.instance.role != ROLE_ADMIN:
            self.fields['role'].choices = [c for c in ROLE_CHOICES if c[0] != ROLE_ADMIN]

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()

    def clean(self):
        data = super().clean()
        email, role = data.get('email'), data.get('role')
        if email and role:
            try:
                validate_email_for_role(email, role)
            except ValidationError as e:
                self.add_error('email', e)
        if role == ROLE_RECEPTIONIST and not data.get('hotel'):
            self.add_error('hotel', "Choisissez l'hôtel où ce réceptionniste travaille.")
        pwd = data.get('password')
        if not self.instance.pk and not pwd:
            self.add_error('password', 'Mot de passe obligatoire.')
        if pwd:
            try:
                validate_password(pwd, self.instance)
            except ValidationError as e:
                self.add_error('password', e)
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get('password'):
            user.set_password(self.cleaned_data['password'])
        # accès à /django-admin/ pour les administrateurs, mais jamais de super-utilisateur créé ici
        user.is_staff = (user.role == ROLE_ADMIN)
        if user.role != ROLE_ADMIN:
            user.is_superuser = False
        if user.role != ROLE_RECEPTIONIST:
            user.hotel = None          # seul un réceptionniste est rattaché à un hôtel
        if commit:
            user.save()
        return user
