"""Test « chaque bouton » : pour chaque rôle, un robot ouvre toutes les pages atteignables par des liens,
puis envoie chaque formulaire / bouton tel qu'il est pré-rempli. Aucune page ne doit planter (500),
afficher du code de gabarit brut ou du texte mal encodé."""
from collections import deque
from datetime import timedelta
from decimal import Decimal
from html.parser import HTMLParser
from urllib.parse import urldefrag, urlencode, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from gestion_hotel.models import BookingPlan, Event, Hotel, HotelService
from gestion_repas.models import Menu, StockProduct
from gestion_rooms.models import Booking, CleaningTask, Invoice, Reservation, Room

User = get_user_model()
PWD = 'Passw0rd!x'
SKIP = ('/static/', '/media/', '/django-admin/', '/logout/')
BAD_MARKERS = ('{{', '{%', 'Ã', 'â€', 'Traceback')


class PageParser(HTMLParser):
    """Collecte les liens et les formulaires (avec leurs valeurs par défaut)."""

    def __init__(self):
        super().__init__()
        self.links, self.forms, self._form, self._select, self._textarea = [], [], None, None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'a' and a.get('href'):
            self.links.append(a['href'])
        elif tag == 'form':
            self._form = {'action': a.get('action') or '', 'method': (a.get('method') or 'get').lower(),
                          'fields': []}
            self.forms.append(self._form)
        elif self._form is None:
            return
        elif tag == 'input' and a.get('name'):
            kind = (a.get('type') or 'text').lower()
            if kind in ('checkbox', 'radio'):
                if 'checked' in a:
                    self._form['fields'].append((a['name'], a.get('value', 'on')))
            elif kind not in ('file', 'submit', 'button', 'image', 'reset'):
                self._form['fields'].append((a['name'], a.get('value', '')))
        elif tag == 'select' and a.get('name'):
            self._select = {'name': a['name'], 'first': None, 'chosen': None}
        elif tag == 'option' and self._select is not None:
            if self._select['first'] is None:
                self._select['first'] = a.get('value', '')
            if 'selected' in a:
                self._select['chosen'] = a.get('value', '')
        elif tag == 'textarea' and a.get('name'):
            self._textarea = [a['name'], '']

    def handle_data(self, data):
        if self._textarea is not None:
            self._textarea[1] += data

    def handle_endtag(self, tag):
        if tag == 'select' and self._select is not None:
            s = self._select
            value = s['chosen'] if s['chosen'] is not None else s['first']
            if value is not None and self._form is not None:
                self._form['fields'].append((s['name'], value))
            self._select = None
        elif tag == 'textarea' and self._textarea is not None:
            if self._form is not None:
                self._form['fields'].append(tuple(self._textarea))
            self._textarea = None
        elif tag == 'form':
            self._form = None


def build_world():
    today = timezone.localdate()

    def user(email, cin, role, hotel=None, prenom='Test'):
        return User.objects.create_user(email, PWD, role=role, cin=cin, nom='Robot', prenom=prenom,
                                        telephone='+21650000000', hotel=hotel)

    admin = User.objects.create_superuser('boss@admin.com', PWD, cin='10000001', nom='Boss', prenom='B',
                                          telephone='+21650000000')
    hotel = Hotel.objects.create(owner=admin, name='Sea Palace', phone='+21671123456', stars=4, country='Tunisie',
                                 city='Hammamet', address='x', description='Hôtel de démonstration.',
                                 completed_step=3, count_normal=3, count_vip=1, price_normal=Decimal('100'),
                                 price_vip=Decimal('250'))
    Hotel.objects.create(owner=admin, name='Brouillon', phone='+21671123456', stars=3, country='T', city='T',
                         address='x', completed_step=1)
    for i in (1, 2, 3):
        Room.objects.create(hotel=hotel, number=f'N00{i}', category='normal', capacity=2, price_per_night=100)
    Room.objects.create(hotel=hotel, number='V001', category='vip', capacity=2, price_per_night=250)
    HotelService.objects.create(hotel=hotel, name='Piscine', price=20, billing='person')
    BookingPlan.objects.create(hotel=hotel, name='Logement seul', supplement=0)
    users = {
        'admin': admin,
        'receptionist': user('recep@service.com', '20000001', 'receptionist', hotel),
        'cleaner': user('clean@service.com', '20000002', 'cleaner'),
        'chef': user('chef@service.com', '20000003', 'chef'),
        'client': user('ali@booking.com', '30000001', 'client', prenom='Ali'),
    }
    guest = users['client']

    def res(number, start, nights, status, paid=False):
        r = Reservation.objects.create(client=guest, room=Room.objects.get(number=number), status=status,
                                       check_in=today + timedelta(days=start),
                                       check_out=today + timedelta(days=start + nights))
        if status != Reservation.PENDING:
            Invoice.objects.create(reservation=r, amount=r.total, status='paid' if paid else 'unpaid',
                                   method='card' if paid else '')
        return r

    booking = Booking.objects.create(client=guest, hotel=hotel, full_name='Ali Robot', booking_type='couple',
                                     persons=2, check_in=today + timedelta(days=5),
                                     check_out=today + timedelta(days=7), total=Decimal('400'))
    Reservation.objects.create(client=guest, room=Room.objects.get(number='N003'), booking=booking,
                               check_in=booking.check_in, check_out=booking.check_out, price_override=400)
    res('N001', 0, 2, Reservation.CONFIRMED)
    res('N002', -2, 2, Reservation.CHECKED_IN, paid=True)
    res('V001', -9, 3, Reservation.CHECKED_OUT, paid=True)
    CleaningTask.objects.create(room=Room.objects.get(number='V001'))
    Event.objects.create(title='Soirée du Nouvel An', start=timezone.now() + timedelta(days=30),
                         location='Salle des fêtes', capacity=100, price=50)
    Menu.objects.create(name='Couscous au poisson', price=25)
    StockProduct.objects.create(name='Tomates', category='legumes', quantity=2, threshold=5)
    return users


class CrawlEveryButtonTests(TestCase):
    max_pages = 400

    def setUp(self):
        self.users = build_world()

    def crawl(self, user):
        """Parcourt tout ce que `user` peut atteindre ; renvoie la liste des problèmes."""
        problems, seen, forms_done = [], set(), set()
        queue = deque(['/', '/dashboard/'] if user else ['/'] + [f'/espace/{s}/' for s in
                                                                 ('client', 'admin', 'reception',
                                                                  'nettoyage', 'cuisine')])

        def fetch(method, url, data=None):
            if user:
                self.client.force_login(user)
            else:
                self.client.logout()
            r = (self.client.post(url, data or {}) if method == 'post'
                 else self.client.get(url, data or {}))
            label = f'{method.upper()} {url}'
            if r.status_code >= 500:
                problems.append(f'{label} -> {r.status_code}')
            body = r.content.decode('utf-8', 'replace') if r.get('Content-Type', '').startswith('text/html') else ''
            for m in BAD_MARKERS:
                if m in body:
                    problems.append(f'{label} -> contient « {m} »')
            return r, body

        def local(href, base):
            href = urldefrag(href)[0]
            if not href or href.startswith(('mailto:', 'tel:', 'javascript:', 'http://', 'https://')):
                return None
            if href.startswith('?'):
                href = urlsplit(base).path + href
            if not href.startswith('/') or href.startswith(SKIP):
                return None
            return href

        while queue and len(seen) < self.max_pages:
            url = queue.popleft()
            if url in seen:
                continue
            seen.add(url)
            r, body = fetch('get', url)
            if r.status_code in (301, 302) and r['Location'].startswith('/'):
                queue.append(r['Location'])
                continue
            if not body:
                continue
            p = PageParser()
            p.feed(body)
            for href in p.links:
                target = local(href, url)
                if target and target not in seen:
                    queue.append(target)
            for f in p.forms:
                action = local(f['action'], url) if f['action'] else urlsplit(url).path
                if not action:
                    continue
                data = [(k, v) for k, v in f['fields'] if k != 'csrfmiddlewaretoken']
                key = (f['method'], action, tuple(sorted(data)))
                if key in forms_done:
                    continue
                forms_done.add(key)
                if f['method'] == 'get':
                    target = action + ('?' + urlencode(data) if data else '')
                    if target not in seen:
                        queue.append(target)
                    continue
                mapping = {}
                for k, v in data:
                    mapping.setdefault(k, []).append(v)
                resp, _ = fetch('post', action, mapping)
                if resp.status_code in (301, 302) and resp['Location'].startswith('/'):
                    queue.append(resp['Location'])
                # la page peut avoir changé (statuts, boutons) : on la revisite une fois
                seen.discard(url) if (url, 'again') not in seen else None
                seen.add((url, 'again'))
        return problems, len([s for s in seen if isinstance(s, str)]), len(forms_done)

    def check(self, role):
        problems, pages, forms = self.crawl(self.users.get(role))
        self.assertGreater(pages, 1, role)
        self.assertEqual(problems, [], f'{role}: {pages} pages, {forms} formulaires')

    def test_anonymous(self):
        self.check(None)

    def test_client(self):
        self.check('client')

    def test_admin(self):
        self.check('admin')

    def test_receptionist(self):
        self.check('receptionist')

    def test_cleaner(self):
        self.check('cleaner')

    def test_chef(self):
        self.check('chef')
