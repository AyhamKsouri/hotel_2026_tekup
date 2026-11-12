"""Espace réceptionniste : chaque réceptionniste ne travaille que pour SON hôtel."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from account.models import Notification
from gestion_hotel.models import Hotel

from . import services
from .models import Booking, CleaningTask, Invoice, Reservation, Room

User = get_user_model()
PWD = 'Passw0rd!x'


class ReceptionBase(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.owner = User.objects.create_user('owner@admin.com', PWD, role='admin', cin='10000001',
                                              nom='Admin', prenom='A', telephone='+21650000000')
        self.hotel_a = self._hotel('Sea Palace', 'A')
        self.hotel_b = self._hotel('Mountain Lodge', 'B')
        self.recep_a = self._user('ra@service.com', '20000011', 'receptionist', self.hotel_a, 'Salma')
        self.recep_a2 = self._user('ra2@service.com', '20000014', 'receptionist', self.hotel_a, 'Nour')
        self.recep_b = self._user('rb@service.com', '20000012', 'receptionist', self.hotel_b, 'Omar')
        self.recep_none = self._user('rn@service.com', '20000013', 'receptionist', None, 'Sans')
        self.cleaner = self._user('c@service.com', '20000015', 'cleaner', None, 'Clean')
        self.guest = self._user('ali@booking.com', '30000001', 'client', None, 'Ali')
        self.guest_b = self._user('bob@booking.com', '30000002', 'client', None, 'Bob')

    def _hotel(self, name, p):
        h = Hotel.objects.create(owner=self.owner, name=name, phone='+21671123456', stars=4, country='Tunisie',
                                 city='Tunis', address='x', completed_step=3, count_normal=2, count_vip=1,
                                 price_normal=Decimal('100'), price_vip=Decimal('200'))
        for n in (1, 2):
            Room.objects.create(hotel=h, number=f'{p}00{n}', category='normal', capacity=2, price_per_night=100)
        Room.objects.create(hotel=h, number=f'{p}V01', category='vip', capacity=2, price_per_night=200)
        return h

    def _user(self, email, cin, role, hotel, prenom):
        return User.objects.create_user(email, PWD, role=role, cin=cin, nom=f'{prenom}son', prenom=prenom,
                                        telephone='+21650000009', hotel=hotel)

    def room(self, number):
        return Room.objects.get(number=number)

    def stay(self, number, start=0, nights=2, client=None, status=Reservation.CONFIRMED, invoice=True, booking=None):
        r = Reservation.objects.create(client=client or self.guest, room=self.room(number), booking=booking,
                                       check_in=self.today + timedelta(days=start),
                                       check_out=self.today + timedelta(days=start + nights), status=status)
        if invoice:
            Invoice.objects.create(reservation=r, amount=r.total)
        return r

    def as_(self, user):
        self.client.force_login(user)
        return self.client


class HotelIsolationTests(ReceptionBase):
    def test_cleaning_tasks_are_scoped_to_own_hotel(self):
        ta = CleaningTask.objects.create(room=self.room('A001'))
        tb = CleaningTask.objects.create(room=self.room('B001'))
        c = self.as_(self.recep_a)
        r = c.get(reverse('cleaning_list'))
        self.assertContains(r, 'A001')
        self.assertNotContains(r, 'B001')
        self.assertEqual(c.get(reverse('cleaning_edit', args=[tb.pk])).status_code, 404)
        self.assertEqual(c.post(reverse('cleaning_delete', args=[tb.pk])).status_code, 404)
        self.assertTrue(CleaningTask.objects.filter(pk=tb.pk).exists())
        form = c.get(reverse('cleaning_add')).context['form']
        self.assertEqual({r.number for r in form.fields['room'].queryset}, {'A001', 'A002', 'AV01'})
        self.assertEqual(c.get(reverse('cleaning_edit', args=[ta.pk])).status_code, 200)

    def test_cleaned_room_notifies_only_receptionists_of_that_hotel(self):
        task = CleaningTask.objects.create(room=self.room('A001'))
        services.mark_cleaned(task)
        notified = set(Notification.objects.filter(message__contains='nettoyée').values_list('user__email', flat=True))
        self.assertEqual(notified, {'ra@service.com', 'ra2@service.com'})

    def test_receptionist_without_hotel_sees_explanation_everywhere(self):
        c = self.as_(self.recep_none)
        for name in ('reservation_list', 'reservation_add', 'invoice_list', 'room_availability', 'cleaning_list',
                     'reception_today', 'reception_calendar', 'reception_clients'):
            r = c.get(reverse(name))
            self.assertEqual(r.status_code, 403, name)
            self.assertContains(r, 'Aucun hôtel assigné', status_code=403)

    def test_other_roles_are_refused(self):
        for user in (self.guest, self.cleaner):
            c = self.as_(user)
            for name in ('reception_today', 'reception_calendar', 'reception_clients', 'reservation_add'):
                self.assertEqual(c.get(reverse(name)).status_code, 403, (user.role, name))

    def test_two_receptionists_of_same_hotel_share_its_data(self):
        r = self.stay('A001')
        self.assertContains(self.as_(self.recep_a2).get(reverse('reservation_list')), 'A001')
        self.assertEqual(self.as_(self.recep_a2).get(reverse('reservation_edit', args=[r.pk])).status_code, 200)

    def test_legacy_client_room_booking_route_is_gone(self):
        with self.assertRaises(NoReverseMatch):
            reverse('client_book')
        self.assertEqual(self.as_(self.guest).get('/rooms/book/').status_code, 404)


class TodayAndCalendarTests(ReceptionBase):
    def test_today_lists_arrivals_departures_and_check_in_returns_here(self):
        arriving = self.stay('A001', start=0)
        leaving = self.stay('A002', start=-2, status=Reservation.CHECKED_IN)
        self.stay('B001', start=0)                                  # autre hôtel : invisible
        c = self.as_(self.recep_a)
        r = c.get(reverse('reception_today'))
        self.assertEqual([x.pk for x in r.context['arrivals']], [arriving.pk])
        self.assertEqual([x.pk for x in r.context['departures']], [leaving.pk])
        self.assertNotContains(r, 'B001')
        today_url = reverse('reception_today')
        r = c.post(reverse('reservation_checkin', args=[arriving.pk]), {'next': today_url})
        self.assertRedirects(r, today_url)
        arriving.refresh_from_db()
        self.assertEqual(arriving.status, Reservation.CHECKED_IN)
        self.assertEqual(self.room('A001').status, Room.OCCUPIED)
        r = c.post(reverse('reservation_checkout', args=[leaving.pk]), {'next': 'https://evil.example/'})
        self.assertRedirects(r, reverse('reservation_list'))       # redirection externe ignorée

    def test_dashboard_counts_arrivals(self):
        self.stay('A001', start=0)
        r = self.as_(self.recep_a).get(reverse('dashboard'))
        self.assertIn(('Arrivées attendues', 1), r.context['stats'])

    def test_calendar_shows_own_rooms_and_bookings(self):
        self.stay('AV01', start=1, nights=3)
        self.stay('B001', start=1)
        c = self.as_(self.recep_a)
        r = c.get(reverse('reception_calendar'))
        self.assertEqual([row['room'].number for row in r.context['grid']], ['A001', 'A002', 'AV01'])
        vip = r.context['grid'][2]['cells']
        self.assertEqual([bool(x['res']) for x in vip[:5]], [False, True, True, True, False])
        self.assertTrue(vip[1]['start'] and not vip[2]['start'])
        self.assertEqual(r.context['free_per_day'][:2], [3, 2])
        self.assertContains(r, 'Alison')
        r = c.get(reverse('reception_calendar'), {'category': 'vip', 'start': 'not-a-date'})
        self.assertEqual(len(r.context['grid']), 1)
        self.assertEqual(r.context['start'], self.today)


class WalkInTests(ReceptionBase):
    def data(self, **over):
        d = {'client_mode': 'existing', 'identifier': self.guest.cin, 'room': self.room('A001').pk,
             'check_in': self.today, 'check_out': self.today + timedelta(days=3)}
        d.update(over)
        return d

    def test_existing_client_by_cin_or_email(self):
        c = self.as_(self.recep_a)
        r = c.post(reverse('reservation_add'), self.data())
        self.assertRedirects(r, reverse('reservation_list'))
        res = Reservation.objects.get()
        self.assertEqual((res.client, res.status, res.total), (self.guest, Reservation.CONFIRMED, Decimal('300')))
        self.assertEqual(res.invoice.amount, Decimal('300'))
        self.assertTrue(Notification.objects.filter(user=self.guest, message__contains='réception').exists())
        r = c.post(reverse('reservation_add'), self.data(identifier='ALI@booking.com', room=self.room('A002').pk,
                                                         amount='250', check_in_now='on'))
        self.assertRedirects(r, reverse('reservation_list'))
        res = Reservation.objects.get(room__number='A002')
        self.assertEqual((res.status, res.total), (Reservation.CHECKED_IN, Decimal('250')))
        self.assertEqual(self.room('A002').status, Room.OCCUPIED)

    def test_new_client_is_created_with_unusable_password(self):
        r = self.as_(self.recep_a).post(reverse('reservation_add'), self.data(
            client_mode='new', identifier='', cin='40000001', nom='Ben Salah', prenom='Ines',
            telephone='+21655111222', email='Ines@booking.com'))
        self.assertRedirects(r, reverse('reservation_list'))
        ines = User.objects.get(cin='40000001')
        self.assertEqual((ines.role, ines.email), ('client', 'ines@booking.com'))
        self.assertFalse(ines.has_usable_password())
        self.assertEqual(Reservation.objects.get().client, ines)

    def test_validation_errors(self):
        c = self.as_(self.recep_a)
        cases = [
            self.data(identifier='99999999'),                                       # client inconnu
            self.data(client_mode='new', identifier='', cin='40000001', nom='X', prenom='Y',
                      telephone='+21655111222', email='x@gmail.com'),                # domaine client imposé
            self.data(client_mode='new', identifier='', cin=self.guest.cin, nom='X', prenom='Y',
                      telephone='+21655111222', email='new@booking.com'),            # CIN déjà utilisé
            self.data(room=self.room('B001').pk),                                    # chambre d'un autre hôtel
            self.data(check_in=self.today - timedelta(days=1)),                      # passé
            self.data(check_out=self.today),                                         # départ <= arrivée
            self.data(check_in=self.today + timedelta(days=1), check_in_now='on'),   # check-in futur
        ]
        for d in cases:
            r = c.post(reverse('reservation_add'), d)
            self.assertEqual(r.status_code, 200, d)
            self.assertTrue(r.context['form'].errors, d)
        self.assertFalse(Reservation.objects.exists())
        self.assertFalse(User.objects.filter(cin='40000001').exists())

    def test_double_booking_refused_and_new_client_rolled_back(self):
        self.stay('A001', start=1, nights=5)
        r = self.as_(self.recep_a).post(reverse('reservation_add'), self.data(
            client_mode='new', identifier='', cin='40000002', nom='N', prenom='P',
            telephone='+21655111222', email='p@booking.com'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'déjà réservée')
        self.assertFalse(User.objects.filter(cin='40000002').exists())
        self.assertEqual(Reservation.objects.count(), 1)

    def test_calendar_prefills_room_and_date(self):
        day = self.today + timedelta(days=4)
        r = self.as_(self.recep_a).get(reverse('reservation_add'),
                                       {'room': self.room('AV01').pk, 'check_in': day.isoformat()})
        self.assertEqual(r.context['form'].initial['check_in'], day.isoformat())


class ReservationEditTests(ReceptionBase):
    def url(self, r):
        return reverse('reservation_edit', args=[r.pk])

    def test_change_dates_room_and_amount_updates_unpaid_invoice(self):
        res = self.stay('A001', start=2)
        r = self.as_(self.recep_a).post(self.url(res), {
            'room': self.room('AV01').pk, 'check_in': res.check_in, 'check_out': res.check_out + timedelta(days=1),
            'amount': '600'})
        self.assertRedirects(r, reverse('reservation_list'))
        res.refresh_from_db()
        self.assertEqual((res.room.number, res.nights, res.total), ('AV01', 3, Decimal('600')))
        self.assertEqual(res.invoice.amount, Decimal('600'))

    def test_overlap_rejected(self):
        self.stay('A002', start=5)
        res = self.stay('A001', start=2)
        r = self.as_(self.recep_a).post(self.url(res), {
            'room': self.room('A002').pk, 'check_in': res.check_in, 'check_out': res.check_out + timedelta(days=3),
            'amount': '500'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'déjà réservée')
        res.refresh_from_db()
        self.assertEqual(res.room.number, 'A001')

    def test_paid_invoice_locks_amount_and_checked_in_locks_room(self):
        res = self.stay('A001', start=-1, nights=2, status=Reservation.CHECKED_IN)
        Invoice.objects.filter(reservation=res).update(status=Invoice.PAID, method='cash')
        r = self.as_(self.recep_a).post(self.url(res), {
            'room': self.room('A002').pk, 'check_in': self.today, 'check_out': res.check_out + timedelta(days=2),
            'amount': '1'})
        self.assertRedirects(r, reverse('reservation_list'))
        res.refresh_from_db()
        self.assertEqual(res.room.number, 'A001')                  # chambre verrouillée pendant le séjour
        self.assertEqual(res.check_in, self.today - timedelta(days=1))
        self.assertEqual(res.nights, 4)
        self.assertEqual(res.invoice.amount, Decimal('200'))       # facture payée inchangée

    def test_scope_and_finished_reservations(self):
        res_b = self.stay('B001')
        self.assertEqual(self.as_(self.recep_a).get(self.url(res_b)).status_code, 404)
        done = self.stay('A001', start=-3, status=Reservation.CHECKED_OUT)
        r = self.client.get(self.url(done), follow=True)
        self.assertContains(r, 'ne peut plus être modifiée')

    def test_cancel_confirmed_removes_unpaid_invoice(self):
        res = self.stay('A001', start=3)
        self.as_(self.recep_a).post(reverse('reservation_cancel', args=[res.pk]))
        self.assertFalse(Invoice.objects.filter(reservation=res).exists())


class ClientProfileTests(ReceptionBase):
    def test_list_only_clients_of_own_hotel_with_search(self):
        self.stay('A001')
        self.stay('B001', client=self.guest_b)
        c = self.as_(self.recep_a)
        r = c.get(reverse('reception_clients'))
        self.assertContains(r, 'Ali Alison')
        self.assertNotContains(r, 'Bob Bobson')
        self.assertContains(c.get(reverse('reception_clients'), {'q': '30000001'}), 'Ali Alison')
        self.assertNotContains(c.get(reverse('reception_clients'), {'q': 'zzz'}), 'Ali Alison')

    def test_detail_history_and_scope(self):
        self.stay('A001', start=-5, status=Reservation.CHECKED_OUT)
        self.stay('A002', start=3)
        self.stay('B001', start=3)                                   # même client, autre hôtel : caché
        c = self.as_(self.recep_a)
        r = c.get(reverse('reception_client_detail', args=[self.guest.pk]))
        self.assertEqual(len(r.context['stays']), 2)
        self.assertEqual((r.context['upcoming'], r.context['nights'], r.context['due']), (1, 2, Decimal('400')))
        self.assertNotContains(r, 'B001')
        self.assertEqual(c.get(reverse('reception_client_detail', args=[self.guest_b.pk])).status_code, 404)
        self.assertEqual(self.as_(self.recep_b).get(
            reverse('reception_client_edit', args=[self.guest_b.pk])).status_code, 404)

    def test_edit_profile(self):
        self.stay('A001')
        url = reverse('reception_client_edit', args=[self.guest.pk])
        c = self.as_(self.recep_a)
        r = c.post(url, {'nom': 'Ben Ali', 'prenom': 'Ali', 'telephone': '+21699000111', 'email': 'ali2@gmail.com'})
        self.assertEqual(r.status_code, 200)                          # domaine client obligatoire
        r = c.post(url, {'nom': 'Ben Ali', 'prenom': 'Ali', 'telephone': '+21699000111', 'email': 'ALI2@booking.com'})
        self.assertRedirects(r, reverse('reception_client_detail', args=[self.guest.pk]))
        self.guest.refresh_from_db()
        self.assertEqual((self.guest.nom, self.guest.telephone, self.guest.email),
                         ('Ben Ali', '+21699000111', 'ali2@booking.com'))


class InvoiceTests(ReceptionBase):
    def test_pay_with_chosen_method(self):
        inv = self.stay('A001').invoice
        c = self.as_(self.recep_a)
        self.assertContains(c.get(reverse('invoice_pay', args=[inv.pk])), 'Carte bancaire')
        r = c.post(reverse('invoice_pay', args=[inv.pk]), {'method': 'bogus'})
        self.assertEqual(r.status_code, 200)
        r = c.post(reverse('invoice_pay', args=[inv.pk]), {'method': 'card'})
        self.assertRedirects(r, reverse('invoice_list'))
        inv.refresh_from_db()
        self.assertEqual((inv.status, inv.method), (Invoice.PAID, 'card'))
        self.assertIsNotNone(inv.paid_at)
        self.assertTrue(Notification.objects.filter(user=self.guest, message__contains='Paiement reçu').exists())
        r = c.get(reverse('invoice_pay', args=[inv.pk]), follow=True)
        self.assertContains(r, 'déjà payée')

    def test_pay_other_hotel_invoice_is_404(self):
        inv = self.stay('B001').invoice
        self.assertEqual(self.as_(self.recep_a).post(reverse('invoice_pay', args=[inv.pk]),
                                                     {'method': 'cash'}).status_code, 404)

    def test_printable_invoice_groups_booking_rooms(self):
        b = Booking.objects.create(client=self.guest, hotel=self.hotel_a, full_name='Famille Ali',
                                   booking_type='family', persons=4, check_in=self.today,
                                   check_out=self.today + timedelta(days=2), total=Decimal('600'))
        r1 = self.stay('A001', booking=b)
        r2 = self.stay('AV01', booking=b)
        services.pay_invoice(r1.invoice, 'cash')
        c = self.as_(self.recep_a)
        r = c.get(reverse('invoice_print', args=[r2.invoice.pk]))
        self.assertEqual(len(r.context['lines']), 2)
        self.assertEqual((r.context['total'], r.context['paid'], r.context['due']),
                         (Decimal('600'), Decimal('200'), Decimal('400')))
        self.assertContains(r, 'Famille Ali')
        self.assertContains(r, f'D{b.pk:05d}')
        # le client imprime sa propre facture, pas celle d'un autre
        self.assertEqual(self.as_(self.guest).get(reverse('invoice_print', args=[r1.invoice.pk])).status_code, 200)
        self.assertEqual(self.as_(self.guest_b).get(reverse('invoice_print', args=[r1.invoice.pk])).status_code, 404)
        self.assertEqual(self.as_(self.recep_b).get(reverse('invoice_print', args=[r1.invoice.pk])).status_code, 404)
