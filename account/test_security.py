"""Failles corrigées lors de l'audit du 12/11/2026 : chaque test rejoue l'attaque et vérifie qu'elle échoue."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from gestion_hotel.models import Hotel
from gestion_rooms.models import Invoice, Reservation, Room

User = get_user_model()
PWD = 'Passw0rd!x'


class SecurityTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.root = User.objects.create_superuser('root@admin.com', PWD, cin='10000001', nom='R', prenom='R',
                                                  telephone='+21650000000')
        self.admin = User.objects.create_user('second@admin.com', PWD, role='admin', cin='10000002', nom='S',
                                              prenom='S', telephone='+21650000000')
        self.hotel = Hotel.objects.create(owner=self.root, name='Sea', phone='+21671123456', stars=4, country='T',
                                          city='T', address='x', completed_step=3, count_normal=2,
                                          price_normal=Decimal('100'))
        self.room = Room.objects.create(hotel=self.hotel, number='N001', category='normal', capacity=2,
                                        price_per_night=100)
        self.recep = User.objects.create_user('r@service.com', PWD, role='receptionist', cin='20000001', nom='R',
                                              prenom='R', telephone='+21650000000', hotel=self.hotel)
        self.guest = User.objects.create_user('g@booking.com', PWD, role='client', cin='30000001', nom='G',
                                              prenom='G', telephone='+21650000000')

    def signup(self, space, email, role_cin='40000001'):
        return self.client.post(reverse('espace', args=[space]), {
            'action': 'signup', 'cin': role_cin, 'nom': 'X', 'prenom': 'Y', 'telephone': '+21650000000',
            'email': email, 'password1': 'Tr3s-S0lide!', 'password2': 'Tr3s-S0lide!'})

    # ---------------------------------------------------------------- comptes
    def test_nobody_can_self_register_as_admin_or_staff(self):
        for space, email in (('admin', 'evil@admin.com'), ('reception', 'evil@service.com'),
                             ('cuisine', 'chef@service.com')):
            self.signup(space, email)
            self.assertFalse(User.objects.filter(email=email).exists(), space)
        with self.settings(ALLOW_STAFF_SIGNUP=True):          # même si l'option est activée…
            self.signup('admin', 'evil@admin.com')
            self.assertFalse(User.objects.filter(email='evil@admin.com').exists())   # …jamais un admin
            self.signup('reception', 'staff@service.com')
            self.assertTrue(User.objects.filter(email='staff@service.com').exists())
        self.signup('client', 'new@booking.com', '40000009')
        self.assertTrue(User.objects.filter(email='new@booking.com', role='client').exists())

    def user_data(self, **over):
        d = {'cin': '50000001', 'nom': 'N', 'prenom': 'P', 'telephone': '+21650000000', 'email': 'n@admin.com',
             'role': 'admin', 'hotel': '', 'password': 'Tr3s-S0lide!', 'is_active': 'on'}
        d.update(over)
        return d

    def test_ordinary_admin_cannot_take_over_other_admins(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('user_edit', args=[self.root.pk])).status_code, 403)
        r = self.client.post(reverse('user_edit', args=[self.root.pk]),
                             self.user_data(cin=self.root.cin, email=self.root.email, password='Hacked-123!'))
        self.assertEqual(r.status_code, 403)
        self.root.refresh_from_db()
        self.assertTrue(self.root.check_password(PWD))
        self.assertEqual(self.client.post(reverse('user_delete', args=[self.root.pk])).status_code, 403)
        # ni créer un administrateur
        self.client.post(reverse('user_add'), self.user_data())
        self.assertFalse(User.objects.filter(email='n@admin.com').exists())
        # mais il gère toujours les employés
        self.assertEqual(self.client.get(reverse('user_edit', args=[self.recep.pk])).status_code, 200)

    def test_admin_created_in_ui_is_never_superuser(self):
        self.client.force_login(self.root)
        self.client.post(reverse('user_add'), self.user_data())
        new = User.objects.get(email='n@admin.com')
        self.assertTrue(new.is_staff)
        self.assertFalse(new.is_superuser)

    # ---------------------------------------------------------------- réception
    def stay(self, start, status=Reservation.CONFIRMED, paid=False):
        r = Reservation.objects.create(client=self.guest, room=self.room, status=status,
                                       check_in=self.today + timedelta(days=start),
                                       check_out=self.today + timedelta(days=start + 2))
        Invoice.objects.create(reservation=r, amount=r.total, status='paid' if paid else 'unpaid',
                               method='cash' if paid else '')
        return r

    def test_no_check_in_before_arrival_date(self):
        r = self.stay(3)
        self.client.force_login(self.recep)
        resp = self.client.post(reverse('reservation_checkin', args=[r.pk]), follow=True)
        self.assertContains(resp, 'avant la date d&#x27;arrivée')
        r.refresh_from_db()
        self.assertEqual(r.status, Reservation.CONFIRMED)

    def test_check_out_warns_about_unpaid_invoice(self):
        r = self.stay(-1, status=Reservation.CHECKED_IN)
        self.client.force_login(self.recep)
        resp = self.client.post(reverse('reservation_checkout', args=[r.pk]), follow=True)
        self.assertContains(resp, 'reste à encaisser')

    def test_room_with_guest_cannot_be_marked_free(self):
        self.stay(-1, status=Reservation.CHECKED_IN)
        Room.objects.filter(pk=self.room.pk).update(status=Room.OCCUPIED)
        self.client.force_login(self.recep)
        resp = self.client.post(reverse('room_mark_available', args=[self.room.pk]), follow=True)
        self.assertContains(resp, 'un client y séjourne')
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, Room.OCCUPIED)

    def test_receptionist_cannot_delete_reservations(self):
        r = self.stay(2)
        self.client.force_login(self.recep)
        self.assertEqual(self.client.post(reverse('reservation_delete', args=[r.pk])).status_code, 403)
        self.assertTrue(Reservation.objects.filter(pk=r.pk).exists())
        self.assertNotContains(self.client.get(reverse('reservation_list')), 'bi-trash')

    def test_paid_invoice_is_frozen_and_amount_not_negative(self):
        paid = self.stay(-5, status=Reservation.CHECKED_OUT, paid=True).invoice
        self.client.force_login(self.recep)
        for name in ('invoice_edit', 'invoice_delete'):
            resp = self.client.post(reverse(name, args=[paid.pk]),
                                    {'reservation': paid.reservation_id, 'amount': '1', 'status': 'unpaid'},
                                    follow=True)
            self.assertContains(resp, 'ne peut plus être modifiée')
        paid.refresh_from_db()
        self.assertEqual((paid.status, paid.amount), ('paid', Decimal('200')))
        unpaid = self.stay(5).invoice
        resp = self.client.post(reverse('invoice_edit', args=[unpaid.pk]),
                                {'reservation': unpaid.reservation_id, 'amount': '-50', 'status': 'unpaid'})
        self.assertEqual(resp.status_code, 200)
        unpaid.refresh_from_db()
        self.assertEqual(unpaid.amount, Decimal('200'))

    # ---------------------------------------------------------------- XSS
    def test_service_names_are_escaped_in_booking_script(self):
        from gestion_hotel.models import HotelService
        HotelService.objects.create(hotel=self.hotel, name='<img src=x onerror=alert(1)>', price=1)
        self.client.force_login(self.guest)
        resp = self.client.get(reverse('client_hotel_book', args=[self.hotel.pk]))
        body = resp.content.decode()
        self.assertNotIn('<img src=x onerror', body)          # jamais brut dans le HTML
        self.assertIn('esc(s.name)', body)                    # et échappé par le script de calcul
