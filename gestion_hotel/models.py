from django.db import models


class Event(models.Model):
    title = models.CharField('titre', max_length=150)
    description = models.TextField(blank=True)
    start = models.DateTimeField('début')
    end = models.DateTimeField('fin', null=True, blank=True)
    location = models.CharField('lieu', max_length=150)
    capacity = models.PositiveIntegerField('capacité', default=50)
    price = models.DecimalField('prix', max_digits=8, decimal_places=2, default=0)

    class Meta:
        ordering = ['start']

    def __str__(self):
        return self.title


# ======================================================================
# Hôtels créés par un administrateur via l'assistant en 3 étapes
# ======================================================================
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator

from account.models import phone_validator

MAX_ROOMS_PER_TYPE = 300


def hotel_image_path(instance, filename):
    return f'hotels/{instance.owner_id}/{filename}'


class Hotel(models.Model):
    """Un hôtel appartient à l'administrateur qui l'a créé.

    `completed_step` : dernière étape validée (0 = rien, 3 = hôtel terminé).
    L'hôtel est créé dès l'étape 1 (brouillon) car les images de l'étape 2
    ne peuvent pas être conservées en session.
    """
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              related_name='hotels', verbose_name='administrateur')
    completed_step = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    # --- Étape 1 : informations générales
    name = models.CharField("nom de l'hôtel", max_length=150)
    phone = models.CharField('numéro de téléphone', max_length=16, validators=[phone_validator])
    stars = models.PositiveSmallIntegerField(
        "nombre d'étoiles", validators=[MinValueValidator(1), MaxValueValidator(5)], default=3)
    country = models.CharField('pays', max_length=80)
    city = models.CharField('ville', max_length=80)
    address = models.CharField('adresse', max_length=255)
    description = models.TextField('description', blank=True)

    # --- Étape 2 : chambres
    image_normal = models.ImageField('image chambre normale', upload_to=hotel_image_path, blank=True)
    image_vip = models.ImageField('image chambre VIP', upload_to=hotel_image_path, blank=True)
    image_couple = models.ImageField('image chambre couple', upload_to=hotel_image_path, blank=True)
    image_family = models.ImageField('image chambre familiale', upload_to=hotel_image_path, blank=True)
    count_normal = models.PositiveSmallIntegerField('nombre de chambres normales', default=0,
                                                    validators=[MaxValueValidator(MAX_ROOMS_PER_TYPE)])
    count_vip = models.PositiveSmallIntegerField('nombre de chambres VIP', default=0,
                                                 validators=[MaxValueValidator(MAX_ROOMS_PER_TYPE)])
    count_couple = models.PositiveSmallIntegerField('nombre de chambres couple', default=0,
                                                    validators=[MaxValueValidator(MAX_ROOMS_PER_TYPE)])
    count_family = models.PositiveSmallIntegerField('nombre de chambres familiales', default=0,
                                                    validators=[MaxValueValidator(MAX_ROOMS_PER_TYPE)])

    # --- Étape 3 : prix par type de chambre (par nuit, TND)
    price_normal = models.DecimalField('prix chambre normale', max_digits=8, decimal_places=2, null=True, blank=True)
    price_vip = models.DecimalField('prix chambre VIP', max_digits=8, decimal_places=2, null=True, blank=True)
    price_couple = models.DecimalField('prix chambre couple', max_digits=8, decimal_places=2, null=True, blank=True)
    price_family = models.DecimalField('prix chambre familiale', max_digits=8, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def total_rooms(self):
        """Nombre total de chambres, toujours calculé côté serveur."""
        return self.count_normal + self.count_vip + self.count_couple + self.count_family

    @property
    def is_complete(self):
        return self.completed_step >= 3

    @property
    def next_step(self):
        return min(self.completed_step + 1, 3)

    def type_images(self):
        return {'normal': self.image_normal, 'vip': self.image_vip,
                'couple': self.image_couple, 'family': self.image_family}

    def slides(self):
        """Diaporama client : photos de l'hôtel puis photo de chaque type de chambre."""
        out = [{'url': g.image.url, 'caption': ''} for g in self.gallery.all()]
        labels = {'normal': 'Chambre normale', 'vip': 'Chambre VIP',
                  'couple': 'Chambre couple', 'family': 'Chambre familiale'}
        for key, img in self.type_images().items():
            if img:
                out.append({'url': img.url, 'caption': labels[key]})
        return out

    def room_types(self):
        """[(clé Room.category, libellé, nombre, prix, capacité)] pour les types utilisés."""
        rows = [('normal', 'Normale', self.count_normal, self.price_normal, 2),
                ('vip', 'VIP', self.count_vip, self.price_vip, 2),
                ('couple', 'Couple', self.count_couple, self.price_couple, 2),
                ('family', 'Familiale', self.count_family, self.price_family, 4)]
        return [r for r in rows if r[2] > 0]


class HotelService(models.Model):
    PER_STAY, PER_NIGHT, PER_PERSON = 'stay', 'night', 'person'
    BILLING_CHOICES = [(PER_STAY, 'par séjour'), (PER_NIGHT, 'par nuit'), (PER_PERSON, 'par personne')]

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='services')
    name = models.CharField('service', max_length=100)
    price = models.DecimalField('prix (TND)', max_digits=8, decimal_places=2,
                                validators=[MinValueValidator(0)], help_text='0 = gratuit')
    billing = models.CharField('facturation', max_length=8, choices=BILLING_CHOICES, default=PER_STAY)

    class Meta:
        ordering = ['id']
        constraints = [models.UniqueConstraint(fields=['hotel', 'name'], name='uniq_service_per_hotel')]

    def __str__(self):
        return f'{self.name} – {self.price} TND'


class BookingPlan(models.Model):
    """Formule de réservation (ex. petit-déjeuner inclus, demi-pension…)."""
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='plans')
    name = models.CharField('formule', max_length=100)
    description = models.CharField(max_length=200, blank=True)
    supplement = models.DecimalField('supplément / nuit (TND)', max_digits=8, decimal_places=2, default=0,
                                     validators=[MinValueValidator(0)],
                                     help_text='Ajouté au prix de la chambre. 0 = inclus dans le prix.')

    class Meta:
        ordering = ['supplement', 'id']
        constraints = [models.UniqueConstraint(fields=['hotel', 'name'], name='uniq_plan_per_hotel')]

    def __str__(self):
        return self.name


MAX_GALLERY_IMAGES = 20


class HotelImage(models.Model):
    """Photo de la galerie d'un hôtel précis."""
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='gallery')
    image = models.ImageField('image', upload_to='hotels/gallery/')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def __str__(self):
        return f'{self.hotel.name} – image {self.pk}'
