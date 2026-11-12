from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

CLIENT_DOMAIN = '@booking.com'
EMPLOYEE_DOMAIN = '@service.com'
ADMIN_DOMAIN = '@admin.com'

ROLE_CLIENT = 'client'
ROLE_ADMIN = 'admin'
ROLE_RECEPTIONIST = 'receptionist'
ROLE_CLEANER = 'cleaner'
ROLE_CHEF = 'chef'

ROLE_CHOICES = [
    (ROLE_CLIENT, 'Client'),
    (ROLE_ADMIN, 'Administrateur'),
    (ROLE_RECEPTIONIST, 'Réceptionniste'),
    (ROLE_CLEANER, 'Agent de nettoyage'),
    (ROLE_CHEF, 'Chef cuisinier'),
]

# Domaine de messagerie obligatoire pour chaque rôle
ROLE_DOMAINS = {
    ROLE_CLIENT: CLIENT_DOMAIN,
    ROLE_ADMIN: ADMIN_DOMAIN,
    ROLE_RECEPTIONIST: EMPLOYEE_DOMAIN,
    ROLE_CLEANER: EMPLOYEE_DOMAIN,
    ROLE_CHEF: EMPLOYEE_DOMAIN,
}

cin_validator = RegexValidator(r'^\d{8}$', 'Le CIN doit contenir exactement 8 chiffres.')
phone_validator = RegexValidator(
    r'^\+?\d{8,15}$', 'Téléphone invalide (8 à 15 chiffres, "+" autorisé au début).')


def validate_email_for_role(email, role):
    """Vérifie que l'e-mail se termine par le domaine imposé par le rôle."""
    domain = ROLE_DOMAINS.get(role)
    if domain and not (email or '').lower().endswith(domain):
        label = dict(ROLE_CHOICES).get(role, role)
        raise ValidationError(f"L'e-mail d'un compte « {label} » doit se terminer par {domain}")


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("L'e-mail est obligatoire")
        email = self.normalize_email(email).lower()
        validate_email_for_role(email, extra.get('role', ROLE_CLIENT))
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault('role', ROLE_CLIENT)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(role=ROLE_ADMIN, is_staff=True, is_superuser=True)
        return self._create(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    cin = models.CharField('CIN', max_length=8, unique=True, validators=[cin_validator])
    nom = models.CharField(max_length=100)
    prenom = models.CharField('prénom', max_length=100)
    telephone = models.CharField('téléphone', max_length=16, validators=[phone_validator])
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_CLIENT)
    # hôtel où travaille le réceptionniste (renseigné par l'administrateur)
    hotel = models.ForeignKey('gestion_hotel.Hotel', null=True, blank=True, on_delete=models.SET_NULL,
                              related_name='staff', verbose_name='hôtel')
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # accès à /django-admin/
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['cin', 'nom', 'prenom', 'telephone']

    class Meta:
        ordering = ['nom', 'prenom']

    def __str__(self):
        return f'{self.prenom} {self.nom}'

    @property
    def full_name(self):
        return f'{self.prenom} {self.nom}'

    def clean(self):
        super().clean()
        if self.email:
            self.email = self.email.lower()
            validate_email_for_role(self.email, self.role)

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.lower()
        super().save(*args, **kwargs)


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.message
