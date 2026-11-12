"""Les 5 « espaces » de connexion du site public (un par rôle)."""
from collections import OrderedDict

from .models import (ROLE_ADMIN, ROLE_CHEF, ROLE_CLEANER, ROLE_CLIENT, ROLE_DOMAINS,
                     ROLE_RECEPTIONIST)

_RAW = [
    ('client', ROLE_CLIENT, 'Espace Client', 'bi-person-heart', '#1f4e8c', '#4f86c6',
     'Réservez votre chambre, suivez vos factures et découvrez nos événements.'),
    ('admin', ROLE_ADMIN, 'Espace Admin', 'bi-shield-lock', '#5b1f6e', '#9b4fc6',
     'Gérez les utilisateurs, les événements et les chambres de l\'hôtel.'),
    ('reception', ROLE_RECEPTIONIST, 'Espace Réception', 'bi-bell', '#0f766e', '#2dd4bf',
     'Réservations, factures de paiement et disponibilité des chambres.'),
    ('nettoyage', ROLE_CLEANER, 'Espace Nettoyage', 'bi-stars', '#b45309', '#fbbf24',
     'Chambres à nettoyer, déjà nettoyées et rappels à l\'heure.'),
    ('cuisine', ROLE_CHEF, 'Espace Cuisine', 'bi-egg-fried', '#b42318', '#f97066',
     'Menu du jour, édition des plats et gestion du stock.'),
]

SPACES = OrderedDict()
for slug, role, title, icon, c1, c2, desc in _RAW:
    SPACES[slug] = {'slug': slug, 'role': role, 'title': title, 'icon': icon, 'c1': c1, 'c2': c2,
                    'desc': desc, 'domain': ROLE_DOMAINS[role]}
