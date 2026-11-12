from django.db import models
from django.db.models import F
from django.utils import timezone


class Menu(models.Model):
    ENTREE, PLAT, DESSERT, BOISSON = 'entree', 'plat', 'dessert', 'boisson'
    CATEGORY_CHOICES = [(ENTREE, 'Entrée'), (PLAT, 'Plat'), (DESSERT, 'Dessert'), (BOISSON, 'Boisson')]

    date = models.DateField(default=timezone.localdate)
    name = models.CharField('nom du plat', max_length=150)
    category = models.CharField('type', max_length=10, choices=CATEGORY_CHOICES, default=PLAT)
    description = models.TextField(blank=True)
    price = models.DecimalField('prix', max_digits=7, decimal_places=2)

    class Meta:
        ordering = ['-date', 'category', 'name']

    def __str__(self):
        return f'{self.name} ({self.date:%d/%m/%Y})'


class StockProduct(models.Model):
    LEGUMES, FRUITS, VIANDE = 'legumes', 'fruits', 'viande'
    CATEGORY_CHOICES = [(LEGUMES, 'Légumes'), (FRUITS, 'Fruits'), (VIANDE, 'Viande')]
    UNIT_CHOICES = [('kg', 'kg'), ('l', 'litre'), ('piece', 'pièce')]

    name = models.CharField('produit', max_length=100)
    category = models.CharField('catégorie', max_length=10, choices=CATEGORY_CHOICES)
    quantity = models.DecimalField('quantité', max_digits=8, decimal_places=2)
    unit = models.CharField('unité', max_length=5, choices=UNIT_CHOICES, default='kg')
    threshold = models.DecimalField('seuil d\'alerte', max_digits=8, decimal_places=2, default=5)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return self.name

    @property
    def is_low(self):
        return self.quantity <= self.threshold
