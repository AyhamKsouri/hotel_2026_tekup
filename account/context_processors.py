from .models import (ROLE_ADMIN, ROLE_CHEF, ROLE_CLEANER, ROLE_CLIENT, ROLE_RECEPTIONIST)

NAV = {
    ROLE_CLIENT: [
        ('Tableau de bord', 'dashboard'),
        ('Hôtels', 'client_hotels'),
        ('Réserver une chambre', 'client_book'),
        ('Mes réservations', 'client_reservations'),
        ('Mes factures', 'client_invoices'),
        ('Événements', 'client_events'),
        ('Menu du jour', 'client_menu'),
    ],
    ROLE_ADMIN: [
        ('Tableau de bord', 'dashboard'),
        ('Mes hôtels', 'hotel_list'),
        ('Utilisateurs', 'user_list'),
        ('Événements', 'event_list'),
        ('Chambres', 'room_list'),
    ],
    ROLE_RECEPTIONIST: [
        ('Tableau de bord', 'dashboard'),
        ('Réservations réclamées', 'claimed_list'),
        ('Toutes les réservations', 'reservation_list'),
        ('Factures de paiement', 'invoice_list'),
        ('Chambres disponibles', 'room_availability'),
        ('Planifier un nettoyage', 'cleaning_list'),
    ],
    ROLE_CLEANER: [
        ('Tableau de bord', 'dashboard'),
        ('Chambres à nettoyer', 'cleaner_todo'),
        ('Chambres déjà nettoyées', 'cleaner_done'),
    ],
    ROLE_CHEF: [
        ('Tableau de bord', 'dashboard'),
        ('Menu d\'aujourd\'hui', 'menu_today'),
        ('Tous les menus', 'menu_list'),
        ('Stock des produits', 'stock_list'),
    ],
}


def navigation(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}
    return {
        'nav_items': NAV.get(user.role, []),
        'unread_notifications': user.notifications.filter(is_read=False).count(),
    }


def site(request):
    from django.conf import settings
    from .spaces import SPACES
    return {'HOTEL_NAME': settings.HOTEL_NAME, 'SPACES': list(SPACES.values())}
