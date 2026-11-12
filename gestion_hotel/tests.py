import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from gestion_rooms.models import Room

from .models import BookingPlan, Hotel, HotelService

User = get_user_model()
TMP_MEDIA = tempfile.mkdtemp()


def png(name='room.png'):
    buf = io.BytesIO()
    Image.new('RGB', (20, 20), 'blue').save(buf, 'PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


def make_admin(n, role='admin'):
    dom = {'admin': '@admin.com', 'client': '@booking.com'}[role]
    return User.objects.create_user(f'u{n}{dom}', 'Passw0rd!x', role=role, cin=f'1000000{n}',
                                    nom='N', prenom='P', telephone='+21650000000')


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class HotelWizardTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.admin = make_admin(1)
        self.client.force_login(self.admin)

    # -- helpers
    def step1(self, **over):
        data = dict(name='Sea Palace', phone='+21671123456', stars=4, country='Tunisie',
                    city='Hammamet', address='Av. de la Plage', description='Face à la mer.')
        data.update(over)
        return self.client.post(reverse('hotel_new'), data)

    def step2(self, hotel, **over):
        data = dict(count_normal=3, count_vip=2, count_couple=1, count_family=2,
                    image_normal=png('n.png'), image_vip=png('v.png'),
                    image_couple=png('c.png'), image_family=png('f.png'))
        data.update(over)
        return self.client.post(reverse('hotel_step', args=[hotel.pk, 2]), data)

    def step3_data(self, **over):
        d = {'price_normal': '120', 'price_vip': '300', 'price_couple': '180', 'price_family': '220',
             'services-TOTAL_FORMS': '2', 'services-INITIAL_FORMS': '0',
             'services-MIN_NUM_FORMS': '0', 'services-MAX_NUM_FORMS': '1000',
             'services-0-name': 'Wi-Fi', 'services-0-price': '0', 'services-0-billing': 'stay',
             'services-1-name': 'Spa', 'services-1-price': '45.50', 'services-1-billing': 'person',
             'plans-TOTAL_FORMS': '2', 'plans-INITIAL_FORMS': '0',
             'plans-MIN_NUM_FORMS': '1', 'plans-MAX_NUM_FORMS': '1000',
             'plans-0-name': 'Logement seul', 'plans-0-description': '', 'plans-0-supplement': '0',
             'plans-1-name': 'Demi-pension', 'plans-1-description': 'x', 'plans-1-supplement': '35'}
        d.update(over)
        return d

    # -- tests
    def test_full_flow_creates_hotel_and_rooms(self):
        r = self.step1()
        hotel = Hotel.objects.get()
        self.assertRedirects(r, reverse('hotel_step', args=[hotel.pk, 2]))
        self.assertEqual((hotel.owner, hotel.completed_step), (self.admin, 1))

        r = self.step2(hotel)
        self.assertRedirects(r, reverse('hotel_step', args=[hotel.pk, 3]))
        hotel.refresh_from_db()
        self.assertEqual(hotel.total_rooms, 8)
        self.assertTrue(hotel.image_normal and hotel.image_vip)

        r = self.client.post(reverse('hotel_step', args=[hotel.pk, 3]), self.step3_data())
        self.assertRedirects(r, reverse('hotel_detail', args=[hotel.pk]))
        hotel.refresh_from_db()
        self.assertTrue(hotel.is_complete)
        self.assertEqual(Room.objects.filter(hotel=hotel).count(), 8)
        self.assertEqual(Room.objects.filter(hotel=hotel, category='vip').count(), 2)
        self.assertEqual(Room.objects.get(hotel=hotel, number='V001').price_per_night, 300)
        self.assertEqual(Room.objects.filter(hotel=hotel, category='family').first().capacity, 4)
        self.assertEqual(HotelService.objects.filter(hotel=hotel).count(), 2)
        self.assertEqual(BookingPlan.objects.filter(hotel=hotel).count(), 2)
        self.assertEqual(self.client.get(reverse('hotel_detail', args=[hotel.pk])).status_code, 200)

    def test_step1_validation(self):
        r = self.step1(phone='abc', stars=9, name='')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Hotel.objects.count(), 0)

    def test_cannot_skip_steps(self):
        self.step1()
        hotel = Hotel.objects.get()
        r = self.client.get(reverse('hotel_step', args=[hotel.pk, 3]))
        self.assertRedirects(r, reverse('hotel_step', args=[hotel.pk, 2]))

    def test_step2_requires_room_and_images(self):
        self.step1()
        hotel = Hotel.objects.get()
        r = self.step2(hotel, count_normal=0, count_vip=0, count_couple=0, count_family=0)
        self.assertEqual(r.status_code, 200)
        r = self.step2(hotel, image_normal='', image_vip='')          # normal/VIP sans image
        self.assertEqual(r.status_code, 200)
        hotel.refresh_from_db()
        self.assertEqual(hotel.completed_step, 1)
        # couple + famille : leurs images sont exigées, pas celles de normal/VIP
        r = self.step2(hotel, count_normal=0, count_vip=0, image_normal='', image_vip='', image_couple='')
        self.assertEqual(r.status_code, 200)
        r = self.step2(hotel, count_normal=0, count_vip=0, image_normal='', image_vip='')
        self.assertEqual(r.status_code, 302)

    def test_step2_rejects_non_image(self):
        self.step1()
        hotel = Hotel.objects.get()
        bad = SimpleUploadedFile('x.png', b'not an image', content_type='image/png')
        r = self.step2(hotel, image_normal=bad)
        self.assertEqual(r.status_code, 200)

    def test_step3_needs_one_plan_and_prices_and_no_dupes(self):
        self.step1()
        hotel = Hotel.objects.get()
        self.step2(hotel)
        url = reverse('hotel_step', args=[hotel.pk, 3])
        # prix manquant
        self.assertEqual(self.client.post(url, self.step3_data(price_vip='')).status_code, 200)
        # aucune formule
        self.assertEqual(self.client.post(url, self.step3_data(**{
            'plans-TOTAL_FORMS': '1', 'plans-0-name': '', 'plans-0-supplement': ''})).status_code, 200)
        # doublon de service
        self.assertEqual(self.client.post(url, self.step3_data(**{'services-1-name': 'wi-fi'})).status_code, 200)
        # prix négatif
        self.assertEqual(self.client.post(url, self.step3_data(**{'services-1-price': '-5'})).status_code, 200)
        hotel.refresh_from_db()
        self.assertFalse(hotel.is_complete)
        self.assertEqual(Room.objects.count(), 0)

    def test_step3_unused_type_has_no_price_field(self):
        self.step1()
        hotel = Hotel.objects.get()
        self.step2(hotel, count_couple=0, count_family=0)
        r = self.client.get(reverse('hotel_step', args=[hotel.pk, 3]))
        self.assertNotContains(r, 'price_couple')
        self.assertContains(r, 'price_vip')

    def test_double_submit_does_not_duplicate_rooms(self):
        self.step1()
        hotel = Hotel.objects.get()
        self.step2(hotel)
        url = reverse('hotel_step', args=[hotel.pk, 3])
        self.client.post(url, self.step3_data())
        self.client.post(url, self.step3_data())
        self.assertEqual(Room.objects.filter(hotel=hotel).count(), 8)

    def test_other_admin_and_client_are_blocked(self):
        self.step1()
        hotel = Hotel.objects.get()
        other = make_admin(2)
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('hotel_step', args=[hotel.pk, 1])).status_code, 404)
        self.assertEqual(self.client.post(reverse('hotel_delete', args=[hotel.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('hotel_list')), 'Sea Palace')
        self.client.force_login(make_admin(3, 'client'))
        self.assertEqual(self.client.get(reverse('hotel_new')).status_code, 403)

    def test_same_room_number_allowed_in_two_hotels(self):
        for _ in range(2):
            self.step1()
        a, b = Hotel.objects.all()
        for h in (a, b):
            self.step2(h, count_normal=1, count_vip=0, count_couple=0, count_family=0)
            self.client.post(reverse('hotel_step', args=[h.pk, 3]), self.step3_data(
                price_vip='', price_couple='', price_family=''))
        self.assertEqual(Room.objects.filter(number='N001').count(), 2)

    def test_delete_and_room_admin_scope(self):
        self.step1()
        hotel = Hotel.objects.get()
        self.step2(hotel)
        self.client.post(reverse('hotel_step', args=[hotel.pk, 3]), self.step3_data())
        self.assertContains(self.client.get(reverse('room_list')), 'Sea Palace')
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)
        self.assertEqual(self.client.get(reverse('home')).status_code, 200)
        self.client.post(reverse('hotel_delete', args=[hotel.pk]))
        self.assertEqual((Hotel.objects.count(), Room.objects.count()), (0, 0))


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class HotelGalleryTests(TestCase):
    def setUp(self):
        self.admin = make_admin(1)
        self.client.force_login(self.admin)
        self.hotel = Hotel.objects.create(owner=self.admin, name='A', phone='+21671123456', stars=3,
                                          country='Tunisie', city='Tunis', address='x', completed_step=2)
        self.other = Hotel.objects.create(owner=self.admin, name='B', phone='+21671123456', stars=3,
                                          country='Tunisie', city='Tunis', address='x', completed_step=2)

    def test_add_multiple_images_linked_to_that_hotel(self):
        r = self.client.post(reverse('hotel_image_add', args=[self.hotel.pk]),
                             {'images': [png('a.png'), png('b.png')]})
        self.assertRedirects(r, reverse('hotel_step', args=[self.hotel.pk, 2]))
        self.assertEqual(self.hotel.gallery.count(), 2)
        self.assertEqual(self.other.gallery.count(), 0)
        self.assertContains(self.client.get(reverse('hotel_step', args=[self.hotel.pk, 2])), 'galleryInput')

    def test_rejects_fake_image(self):
        bad = SimpleUploadedFile('x.png', b'nope', content_type='image/png')
        self.client.post(reverse('hotel_image_add', args=[self.hotel.pk]), {'images': [bad]})
        self.assertEqual(self.hotel.gallery.count(), 0)

    def test_delete_and_ownership(self):
        self.client.post(reverse('hotel_image_add', args=[self.hotel.pk]), {'images': [png()]})
        img = self.hotel.gallery.get()
        # image d'un autre hôtel : introuvable via cet hôtel
        self.assertEqual(self.client.post(reverse('hotel_image_delete', args=[self.other.pk, img.pk])).status_code, 404)
        # autre admin : 404
        self.client.force_login(make_admin(2))
        self.assertEqual(self.client.post(reverse('hotel_image_add', args=[self.hotel.pk]), {'images': [png()]}).status_code, 404)
        self.assertEqual(self.client.post(reverse('hotel_image_delete', args=[self.hotel.pk, img.pk])).status_code, 404)
        self.client.force_login(self.admin)
        self.client.post(reverse('hotel_image_delete', args=[self.hotel.pk, img.pk]))
        self.assertEqual(self.hotel.gallery.count(), 0)

    def test_gallery_on_completed_hotel_detail(self):
        self.hotel.completed_step = 3
        self.hotel.save()
        r = self.client.post(reverse('hotel_image_add', args=[self.hotel.pk]), {'images': [png()]})
        self.assertRedirects(r, reverse('hotel_detail', args=[self.hotel.pk]))
        self.assertContains(self.client.get(reverse('hotel_detail', args=[self.hotel.pk])), 'galleryInput')


# ======================================================================== espace client
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from account.models import Notification
from gestion_rooms import services as room_services
from gestion_rooms.models import Booking, Invoice, Reservation


class ClientBookingTests(TestCase):
    def setUp(self):
        self.owner = make_admin(1)
        self.recep = User.objects.create_user('r@service.com', 'Passw0rd!x', role='receptionist', cin='20000001',
                                              nom='R', prenom='R', telephone='+21650000001')
        self.hotel = Hotel.objects.create(
            owner=self.owner, name='Sea Palace', phone='+21671123456', stars=4, country='Tunisie', city='Hammamet',
            address='x', description='Face à la mer.', completed_step=3, count_normal=3, count_vip=1,
            price_normal=Decimal('100'), price_vip=Decimal('200'))
        for i in range(1, 4):
            Room.objects.create(hotel=self.hotel, number=f'N00{i}', category='normal', capacity=2,
                                price_per_night=100)
        Room.objects.create(hotel=self.hotel, number='V001', category='vip', capacity=2, price_per_night=200)
        self.recep.hotel = self.hotel      # un réceptionniste n'est prévenu que pour SON hôtel
        self.recep.save(update_fields=['hotel'])
        self.pool = HotelService.objects.create(hotel=self.hotel, name='Piscine', price=100, billing='stay')
        self.event = HotelService.objects.create(hotel=self.hotel, name='Événements', price=70, billing='stay')
        self.resto = HotelService.objects.create(hotel=self.hotel, name='Restaurant', price=50, billing='person')
        other = Hotel.objects.create(owner=self.owner, name='Autre', phone='+21671123456', stars=3, country='T',
                                     city='T', address='x', completed_step=3, count_normal=1,
                                     price_normal=Decimal('10'))
        self.foreign_service = HotelService.objects.create(hotel=other, name='Spa', price=999, billing='stay')
        self.user = make_admin(5, 'client')
        self.client.force_login(self.user)
        self.today = timezone.localdate()

    def data(self, **over):
        d = {'full_name': 'Ali Ben Salah', 'booking_type': 'family',
             'check_in': self.today + timedelta(days=10), 'check_out': self.today + timedelta(days=12),
             'persons': 4, 'has_children': 'on', 'children_count': 2, 'child_age': ['5', '14'],
             'rooms_count': 2, 'room_type': ['normal', 'vip'], 'services': [self.pool.pk]}
        d.update(over)
        return d

    def book(self, **over):
        return self.client.post(reverse('client_hotel_book', args=[self.hotel.pk]), self.data(**over))

    def test_price_formula_free_child_and_services(self):
        r = self.book()
        self.assertRedirects(r, reverse('client_reservations'))
        b = Booking.objects.get()
        # 4 personnes - 1 enfant < 11 ans = 3 payantes ; 2 nuits
        # normale 100×2×3=600 ; VIP 200×2×3=1200 ; piscine 100
        self.assertEqual(b.total, Decimal('1900.00'))
        self.assertEqual(b.children_ages, [5, 14])
        lines = list(b.reservations.order_by('id'))
        self.assertEqual([x.room.category for x in lines], ['normal', 'vip'])
        self.assertEqual([x.price_override for x in lines], [Decimal('700.00'), Decimal('1200.00')])
        self.assertEqual(sum(x.total for x in lines), b.total)
        self.assertTrue(all(x.status == Reservation.PENDING for x in lines))

    def test_per_person_service_and_other_hotel_service_ignored(self):
        # 3 personnes dont un enfant de 5 ans (gratuit) : 2 payantes, une chambre normale (2 places) suffit
        self.book(services=[self.resto.pk, self.foreign_service.pk], rooms_count=1, room_type=['normal'],
                  persons=3, children_count=1, child_age=['5'])
        b = Booking.objects.get()
        # 100 × 2 nuits × 2 payantes = 400 + restaurant 50 × 2 ; le service d'un autre hôtel est ignoré
        self.assertEqual(b.total, Decimal('500.00'))
        self.assertEqual([e['name'] for e in b.extras], ['Restaurant'])

    def test_room_capacity_is_enforced(self):
        r = self.book(has_children='', children_count='', child_age=[], persons=5, rooms_count=2,
                      room_type=['normal', 'vip'], services=[])
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'accueillent 4 personnes au maximum')
        self.assertFalse(Booking.objects.exists())

    def test_no_children_all_pay(self):
        self.book(has_children='', children_count='', child_age=[], persons=2, rooms_count=1,
                  room_type=['vip'], services=[])
        self.assertEqual(Booking.objects.get().total, Decimal('800.00'))   # 200 × 2 nuits × 2

    def test_reception_flow_invoices_sum_to_total(self):
        self.book()
        for res in Reservation.objects.all():
            room_services.confirm_reservation(res)
        self.assertEqual(sum(i.amount for i in Invoice.objects.all()), Booking.objects.get().total)
        self.assertEqual(self.client.get(reverse('client_reservations')).status_code, 200)
        self.assertTrue(Notification.objects.filter(user=self.recep, message__contains='Nouvelle réservation').exists())
        self.assertTrue(Notification.objects.filter(user=self.owner).exists())

    def test_availability_overlap_and_free_after(self):
        self.book(rooms_count=1, room_type=['vip'], has_children='', children_count='', child_age=[], persons=2)
        self.assertEqual(Booking.objects.count(), 1)
        r = self.book(rooms_count=1, room_type=['vip'], has_children='', children_count='', child_age=[], persons=2)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'disponible')
        self.assertEqual(Booking.objects.count(), 1)
        # dates qui s'enchaînent : la chambre est libre
        r = self.book(rooms_count=1, room_type=['vip'], has_children='', children_count='', child_age=[], persons=2,
                      check_in=self.today + timedelta(days=12), check_out=self.today + timedelta(days=13))
        self.assertEqual(r.status_code, 302)
        # plus de chambres normales que disponibles (3)
        r = self.book(rooms_count=4, room_type=['normal'] * 4, check_in=self.today + timedelta(days=30),
                      check_out=self.today + timedelta(days=31))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Booking.objects.count(), 2)

    def test_validation(self):
        n = lambda r: (r.status_code, Booking.objects.count())
        self.assertEqual(n(self.book(child_age=['5'])), (200, 0))                       # âge manquant
        self.assertEqual(n(self.book(child_age=['5', 'x'])), (200, 0))                  # âge invalide
        self.assertEqual(n(self.book(persons=2)), (200, 0))                             # pas d'adulte
        self.assertEqual(n(self.book(check_in=self.today - timedelta(days=1))), (200, 0))
        self.assertEqual(n(self.book(check_out=self.today + timedelta(days=10))), (200, 0))
        self.assertEqual(n(self.book(room_type=['normal'])), (200, 0))                  # 1 type pour 2 chambres
        self.assertEqual(n(self.book(room_type=['normal', 'couple'])), (200, 0))        # type absent de l'hôtel
        self.assertEqual(n(self.book(full_name='')), (200, 0))

    def test_browse_pages_and_access(self):
        draft = Hotel.objects.create(owner=self.owner, name='Brouillon', phone='+21671123456', stars=3,
                                     country='T', city='T', address='x', completed_step=2)
        for mode in ('cards', 'list'):
            r = self.client.get(reverse('client_hotels') + f'?view={mode}')
            self.assertContains(r, 'Sea Palace')
            self.assertContains(r, '+21671123456')
            self.assertNotContains(r, 'Brouillon')
            self.assertContains(r, reverse('client_hotel_book', args=[self.hotel.pk]))
            self.assertContains(r, reverse('client_hotel_detail', args=[self.hotel.pk]))
        r = self.client.get(reverse('client_hotel_detail', args=[self.hotel.pk]))
        self.assertContains(r, 'Face à la mer.')
        self.assertEqual(self.client.get(reverse('client_hotel_detail', args=[draft.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('client_hotel_book', args=[draft.pk])).status_code, 404)
        self.assertContains(self.client.get(reverse('client_hotel_book', args=[self.hotel.pk])), 'Piscine')
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse('client_hotels')).status_code, 403)

    def test_slides_carousel_two_seconds(self):
        self.hotel.gallery.create(image=png('g.png'))
        self.hotel.image_vip = png('v.png')
        self.hotel.save()
        r = self.client.get(reverse('client_hotels'))
        self.assertContains(r, 'data-bs-interval="2000"')
        self.assertEqual(len(self.hotel.slides()), 2)
        self.assertEqual(self.hotel.slides()[1]['caption'], 'Chambre VIP')



class ReceptionClaimsTests(TestCase):
    """Réservations réclamées : le réceptionniste de l'hôtel confirme ou refuse ; périmètre = son hôtel."""

    def setUp(self):
        self.owner = make_admin(1)
        self.today = timezone.localdate()
        self.hotel_a = self._hotel('Sea Palace', 'A')
        self.hotel_b = self._hotel('Mountain Lodge', 'B')
        self.recep_a = self._staff('ra@service.com', '20000011', self.hotel_a, 'Salma', 'Trabelsi')
        self.recep_b = self._staff('rb@service.com', '20000012', self.hotel_b, 'Omar', 'Gharbi')
        self.recep_none = self._staff('rn@service.com', '20000013', None, 'Sans', 'Hotel')
        self.guest = make_admin(5, 'client')

    def _hotel(self, name, prefix):
        h = Hotel.objects.create(
            owner=self.owner, name=name, phone='+21671123456', stars=4, country='Tunisie', city='Tunis',
            address='x', completed_step=3, count_normal=2, count_vip=1,
            price_normal=Decimal('100'), price_vip=Decimal('200'))
        for i in (1, 2):
            Room.objects.create(hotel=h, number=f'{prefix}00{i}', category='normal', capacity=2, price_per_night=100)
        Room.objects.create(hotel=h, number=f'{prefix}V01', category='vip', capacity=2, price_per_night=200)
        return h

    def _staff(self, email, cin, hotel, prenom, nom):
        return User.objects.create_user(email, 'Passw0rd!x', role='receptionist', cin=cin, nom=nom,
                                        prenom=prenom, telephone='+21650000009', hotel=hotel)

    def book(self, hotel, name='Ali Ben Salah', rooms=('normal', 'vip'), start=10, nights=2):
        self.client.force_login(self.guest)
        r = self.client.post(reverse('client_hotel_book', args=[hotel.pk]), {
            'full_name': name, 'booking_type': 'couple', 'persons': 2, 'rooms_count': len(rooms),
            'room_type': list(rooms), 'check_in': self.today + timedelta(days=start),
            'check_out': self.today + timedelta(days=start + nights)})
        self.assertEqual(r.status_code, 302, getattr(r, 'context', None) and r.context['form'].errors)
        return Booking.objects.filter(hotel=hotel).latest('pk')

    def as_(self, user):
        self.client.force_login(user)
        return self.client

    # ---- dashboard
    def test_dashboard_shows_full_name_and_hotel(self):
        r = self.as_(self.recep_a).get(reverse('dashboard'))
        self.assertContains(r, 'Salma Trabelsi')
        self.assertContains(r, 'Sea Palace')
        self.assertNotContains(r, 'Mountain Lodge')
        r = self.as_(self.recep_none).get(reverse('dashboard'))
        self.assertContains(r, 'Aucun hôtel assigné')

    def test_dashboard_counts_claims_of_own_hotel(self):
        self.book(self.hotel_a)          # 1 demande (2 chambres)
        self.book(self.hotel_b)
        r = self.as_(self.recep_a).get(reverse('dashboard'))
        self.assertIn(('Réservations réclamées', 1), r.context['stats'])

    # ---- liste des réclamées
    def test_claimed_list_only_own_hotel(self):
        ba = self.book(self.hotel_a, name='Client Alpha')
        bb = self.book(self.hotel_b, name='Client Bravo')
        r = self.as_(self.recep_a).get(reverse('claimed_list'))
        self.assertContains(r, 'Client Alpha')
        self.assertContains(r, f'Demande #{ba.pk}')
        self.assertContains(r, '2 nuits')                       # durée = départ − arrivée
        self.assertNotContains(r, 'Client Bravo')
        r = self.as_(self.recep_b).get(reverse('claimed_list'))
        self.assertContains(r, f'Demande #{bb.pk}')
        self.assertNotContains(r, 'Client Alpha')

    def test_claimed_list_without_hotel_and_access(self):
        self.book(self.hotel_a)
        r = self.as_(self.recep_none).get(reverse('claimed_list'))
        self.assertContains(r, 'Aucun hôtel ne vous est assigné')
        self.assertEqual(len(r.context['claims']), 0)
        self.assertEqual(self.as_(self.guest).get(reverse('claimed_list')).status_code, 403)
        self.assertEqual(self.as_(self.owner).get(reverse('claimed_list')).status_code, 403)

    # ---- confirmer
    def test_confirm_claim_confirms_all_rooms_and_bills(self):
        b = self.book(self.hotel_a)
        first = b.reservations.order_by('pk').first()
        r = self.as_(self.recep_a).post(reverse('claimed_confirm', args=[first.pk]))
        self.assertRedirects(r, reverse('claimed_list'))
        self.assertEqual(set(b.reservations.values_list('status', flat=True)), {Reservation.CONFIRMED})
        self.assertEqual(sum(i.amount for i in Invoice.objects.all()), b.total)
        self.assertEqual(Invoice.objects.count(), 2)
        notes = Notification.objects.filter(user=self.guest, message__contains='confirmée')
        self.assertEqual(notes.count(), 1)                       # une seule notification par demande
        self.assertContains(self.client.get(reverse('claimed_list')), 'Aucune réservation réclamée')

    def test_decide_twice_is_rejected(self):
        b = self.book(self.hotel_a)
        pk = b.reservations.first().pk
        self.as_(self.recep_a).post(reverse('claimed_confirm', args=[pk]))
        r = self.client.post(reverse('claimed_confirm', args=[pk]), follow=True)
        self.assertContains(r, 'déjà été traitée')
        r = self.client.post(reverse('claimed_refuse', args=[pk]), follow=True)
        self.assertContains(r, 'déjà été traitée')
        self.assertEqual(Invoice.objects.count(), 2)
        self.assertEqual(set(b.reservations.values_list('status', flat=True)), {Reservation.CONFIRMED})

    # ---- refuser
    def test_refuse_claim_changes_status_and_frees_rooms(self):
        b = self.book(self.hotel_a, rooms=('vip',))
        res = b.reservations.get()
        r = self.as_(self.recep_a).post(reverse('claimed_refuse', args=[res.pk]))
        self.assertRedirects(r, reverse('claimed_list'))
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.REFUSED)
        self.assertEqual(res.get_status_display(), 'Refusée')
        self.assertFalse(Invoice.objects.exists())
        self.assertTrue(Notification.objects.filter(user=self.guest, message__contains='refusée').exists())
        # la chambre VIP unique est de nouveau réservable sur les mêmes dates
        self.book(self.hotel_a, rooms=('vip',))
        self.assertEqual(Booking.objects.filter(hotel=self.hotel_a).count(), 2)

    # ---- sécurité / périmètre
    def test_other_hotel_receptionist_cannot_decide(self):
        b = self.book(self.hotel_a)
        pk = b.reservations.first().pk
        self.assertEqual(self.as_(self.recep_b).post(reverse('claimed_confirm', args=[pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('claimed_refuse', args=[pk])).status_code, 404)
        self.assertEqual(self.as_(self.recep_none).post(reverse('claimed_confirm', args=[pk])).status_code, 403)
        self.assertEqual(self.as_(self.guest).post(reverse('claimed_confirm', args=[pk])).status_code, 403)
        self.assertEqual(set(b.reservations.values_list('status', flat=True)), {Reservation.PENDING})

    def test_decision_requires_post(self):
        pk = self.book(self.hotel_a).reservations.first().pk
        c = self.as_(self.recep_a)
        self.assertEqual(c.get(reverse('claimed_confirm', args=[pk])).status_code, 405)
        self.assertEqual(c.get(reverse('claimed_refuse', args=[pk])).status_code, 405)

    def test_new_booking_notifies_only_receptionists_of_that_hotel(self):
        self.book(self.hotel_a)
        self.assertTrue(Notification.objects.filter(user=self.recep_a, message__contains='Nouvelle réservation').exists())
        self.assertFalse(Notification.objects.filter(user=self.recep_b).exists())
        self.assertFalse(Notification.objects.filter(user=self.recep_none).exists())

    def test_classic_reception_pages_are_scoped_to_own_hotel(self):
        b = self.book(self.hotel_a)
        res = b.reservations.first()
        r = self.as_(self.recep_a).get(reverse('reservation_list'))
        self.assertContains(r, 'A001')
        r = self.as_(self.recep_b).get(reverse('reservation_list'))
        self.assertNotContains(r, 'A001')
        self.assertEqual(self.client.post(reverse('reservation_confirm', args=[res.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('reservation_edit', args=[res.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('room_availability')), 'A001')
        self.assertContains(self.as_(self.recep_a).get(reverse('room_availability')), 'A001')

    # ---- l'admin rattache un réceptionniste à un hôtel
    def user_data(self, **over):
        d = {'cin': '20000077', 'nom': 'Nouveau', 'prenom': 'Recep', 'telephone': '+21650000077',
             'email': 'new@service.com', 'role': 'receptionist', 'hotel': self.hotel_a.pk,
             'password': 'Passw0rd!x', 'is_active': 'on'}
        d.update(over)
        return d

    def test_admin_must_assign_hotel_to_receptionist(self):
        c = self.as_(self.owner)
        r = c.post(reverse('user_add'), self.user_data(hotel=''))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(email='new@service.com').exists())
        r = c.post(reverse('user_add'), self.user_data())
        self.assertRedirects(r, reverse('user_list'))
        self.assertEqual(User.objects.get(email='new@service.com').hotel, self.hotel_a)
        self.assertContains(c.get(reverse('user_list')), 'Sea Palace')

    def test_admin_can_only_use_own_hotels_and_hotel_cleared_for_other_roles(self):
        other_admin = make_admin(2)
        foreign = Hotel.objects.create(owner=other_admin, name='Hotel Etranger', phone='+21671123456', stars=3,
                                       country='T', city='T', address='x', completed_step=3)
        c = self.as_(self.owner)
        r = c.post(reverse('user_add'), self.user_data(hotel=foreign.pk))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(email='new@service.com').exists())
        # un employé non réceptionniste n'a pas d'hôtel
        c.post(reverse('user_edit', args=[self.recep_a.pk]), self.user_data(
            cin=self.recep_a.cin, email=self.recep_a.email, role='cleaner', password=''))
        self.recep_a.refresh_from_db()
        self.assertEqual(self.recep_a.role, 'cleaner')
        self.assertIsNone(self.recep_a.hotel)

    # ---- dates / durée automatique
    def test_booking_page_has_two_dates_and_auto_duration(self):
        self.client.force_login(self.guest)
        r = self.client.get(reverse('client_hotel_book', args=[self.hotel_a.pk]))
        for needle in ('id="id_check_in"', 'id="id_check_out"', 'id="id_duration"', 'readonly'):
            self.assertContains(r, needle)
        self.assertContains(self.as_(self.owner).get(reverse('reservation_add')), 'id_check_out')
