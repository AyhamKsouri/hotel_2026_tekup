import io
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from account.models import (ROLE_ADMIN, ROLE_CHEF, ROLE_CLEANER, ROLE_CLIENT,
                            ROLE_RECEPTIONIST)

from .models import Menu, StockProduct

User = get_user_model()
PWD = 'Passw0rd!x'
TMP_MEDIA = tempfile.mkdtemp()


def make_image(name='pic.png', size=(24, 24), color='tomato'):
    buf = io.BytesIO()
    Image.new('RGB', size, color).save(buf, 'PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class ChefSpaceTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.today = timezone.localdate()
        self.chef = User.objects.create_user(
            'chef@service.com', PWD, role=ROLE_CHEF, cin='20000010',
            nom='Chef', prenom='Amine', telephone='+21650000010',
        )
        self.client_user = User.objects.create_user(
            'client@booking.com', PWD, role=ROLE_CLIENT, cin='30000010',
            nom='Client', prenom='Sami', telephone='+21650000011',
        )
        self.admin = User.objects.create_superuser(
            'boss@admin.com', PWD, cin='10000010', nom='Admin', prenom='Boss',
            telephone='+21650000012',
        )
        self.recep = User.objects.create_user(
            'recep@service.com', PWD, role=ROLE_RECEPTIONIST, cin='20000011',
            nom='Recep', prenom='Lina', telephone='+21650000013',
        )
        self.cleaner = User.objects.create_user(
            'clean@service.com', PWD, role=ROLE_CLEANER, cin='20000012',
            nom='Clean', prenom='Nour', telephone='+21650000014',
        )

    # ------------------------------------------------------------------ Contrôle d'accès
    def test_only_chef_can_access_chef_crud(self):
        menu = Menu.objects.create(date=self.today, name='Salade', price=Decimal('12.00'))
        stock = StockProduct.objects.create(name='Tomates', category=StockProduct.LEGUMES, quantity=10)
        urls = [
            reverse('menu_today'),
            reverse('menu_today_add'),
            reverse('menu_today_edit', args=[menu.pk]),
            reverse('menu_today_delete', args=[menu.pk]),
            reverse('menu_list'),
            reverse('menu_add'),
            reverse('menu_edit', args=[menu.pk]),
            reverse('menu_delete', args=[menu.pk]),
            reverse('stock_list'),
            reverse('stock_add'),
            reverse('stock_edit', args=[stock.pk]),
            reverse('stock_delete', args=[stock.pk]),
        ]
        for url in urls:
            self.client.logout()
            self.assertEqual(self.client.get(url).status_code, 302, url)
            for other in (self.client_user, self.admin, self.recep, self.cleaner):
                self.client.force_login(other)
                self.assertEqual(self.client.get(url).status_code, 403, f'{other.role} -> {url}')

    def test_chef_cannot_access_other_roles_pages(self):
        self.client.force_login(self.chef)
        for url_name in ('user_list', 'hotel_list', 'reception_today', 'cleaner_todo'):
            self.assertEqual(self.client.get(reverse(url_name)).status_code, 403, url_name)

    # ------------------------------------------------------------------ Dashboard chef
    def test_chef_dashboard_displays_today_menu_and_low_stock(self):
        Menu.objects.create(
            date=self.today, name='Couscous Royal', category=Menu.PLAT,
            image=make_image('couscous.png'),
        )
        Menu.objects.create(
            date=self.today - timedelta(days=1), name='Ancien Plat',
        )
        StockProduct.objects.create(
            name='Carottes', category=StockProduct.LEGUMES, quantity=2, threshold=5,
            image=make_image('carottes.png'),
        )
        StockProduct.objects.create(
            name='Pommes', category=StockProduct.FRUITS, quantity=20, threshold=5,
        )
        self.client.force_login(self.chef)
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Tableau de bord du chef')
        self.assertContains(resp, 'Couscous Royal')
        self.assertNotContains(resp, 'Ancien Plat')
        self.assertNotContains(resp, 'TND')
        self.assertContains(resp, 'Carottes')
        self.assertContains(resp, 'Alertes stock bas')
        self.assertEqual(resp.context['stats'], [
            ("Plats aujourd'hui", 1),
            ('Tous les plats', 2),
            ('Produits en stock', 2),
            ('Alertes stock bas', 1),
        ])

    # ------------------------------------------------------------------ CRUD Menu d'aujourd'hui
    def test_menu_today_crud_with_local_image(self):
        self.client.force_login(self.chef)

        # Le champ prix n'est pas saisi par le chef
        get_add = self.client.get(reverse('menu_today_add'))
        self.assertNotContains(get_add, 'name="price"')

        # Create (even if tampered date sent, today_only locks date to today)
        resp = self.client.post(reverse('menu_today_add'), {
            'date': (self.today + timedelta(days=5)).isoformat(),
            'name': 'Brik à l\'oeuf',
            'category': Menu.ENTREE,
            'description': 'Feuille de brik croustillante',
            'image': make_image('brik.png'),
        })
        self.assertRedirects(resp, reverse('menu_today'))
        dish = Menu.objects.get(name="Brik à l'oeuf")
        self.assertEqual(dish.date, self.today)
        self.assertEqual(dish.price, Decimal('0'))
        self.assertTrue(bool(dish.image))

        # Read + filter
        list_resp = self.client.get(reverse('menu_today'), {'category': Menu.ENTREE, 'q': 'Brik'})
        self.assertContains(list_resp, dish.image.url)
        self.assertNotContains(list_resp, 'TND')

        # Update + clear image
        edit_resp = self.client.post(reverse('menu_today_edit', args=[dish.pk]), {
            'name': 'Brik au thon',
            'category': Menu.ENTREE,
            'description': 'Avec câpres',
            'image-clear': 'on',
        })
        self.assertRedirects(edit_resp, reverse('menu_today'))
        dish.refresh_from_db()
        self.assertEqual(dish.name, 'Brik au thon')
        self.assertFalse(bool(dish.image))

        # Yesterday's dish is NOT editable/deletable via menu_today_*
        old = Menu.objects.create(date=self.today - timedelta(days=1), name='Hier')
        self.assertEqual(self.client.get(reverse('menu_today_edit', args=[old.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('menu_today_delete', args=[old.pk])).status_code, 404)

        # Delete
        del_resp = self.client.post(reverse('menu_today_delete', args=[dish.pk]))
        self.assertRedirects(del_resp, reverse('menu_today'))
        self.assertFalse(Menu.objects.filter(pk=dish.pk).exists())

    # ------------------------------------------------------------------ CRUD Tous les menus
    def test_all_menus_crud_with_local_image(self):
        self.client.force_login(self.chef)
        tomorrow = self.today + timedelta(days=1)

        get_add = self.client.get(reverse('menu_add'))
        self.assertNotContains(get_add, 'name="price"')

        # Create
        resp = self.client.post(reverse('menu_add'), {
            'date': tomorrow.isoformat(),
            'name': 'Dorade grillée',
            'category': Menu.PLAT,
            'description': 'Avec légumes sautés',
            'image': make_image('dorade.png'),
        })
        self.assertRedirects(resp, reverse('menu_list'))
        dish = Menu.objects.get(name='Dorade grillée')
        self.assertEqual(dish.date, tomorrow)
        self.assertEqual(dish.price, Decimal('0'))
        self.assertTrue(bool(dish.image))

        # Read + date filter
        r_list = self.client.get(reverse('menu_list'), {'date': tomorrow.isoformat()})
        self.assertContains(r_list, 'Dorade grillée')
        self.assertContains(r_list, dish.image.url)
        self.assertNotContains(r_list, 'TND')

        # Update with new image
        resp = self.client.post(reverse('menu_edit', args=[dish.pk]), {
            'date': tomorrow.isoformat(),
            'name': 'Loup grillé',
            'category': Menu.PLAT,
            'description': 'Citron & herbes',
            'image': make_image('loup.png'),
        })
        self.assertRedirects(resp, reverse('menu_list'))
        dish.refresh_from_db()
        self.assertEqual(dish.name, 'Loup grillé')
        self.assertIn('loup', dish.image.name)

        # Delete
        resp = self.client.post(reverse('menu_delete', args=[dish.pk]))
        self.assertRedirects(resp, reverse('menu_list'))
        self.assertFalse(Menu.objects.filter(pk=dish.pk).exists())

    # ------------------------------------------------------------------ CRUD Stock des produits
    def test_stock_crud_with_local_image_and_validation(self):
        self.client.force_login(self.chef)

        # Create
        resp = self.client.post(reverse('stock_add'), {
            'name': 'Filet de boeuf',
            'category': StockProduct.VIANDE,
            'quantity': '3.50',
            'unit': 'kg',
            'threshold': '5.00',
            'image': make_image('boeuf.png'),
        })
        self.assertRedirects(resp, reverse('stock_list'))
        prod = StockProduct.objects.get(name='Filet de boeuf')
        self.assertTrue(prod.is_low)
        self.assertTrue(bool(prod.image))

        # Read + low filter
        r_low = self.client.get(reverse('stock_list'), {'low': '1', 'category': StockProduct.VIANDE})
        self.assertContains(r_low, 'Filet de boeuf')
        self.assertContains(r_low, prod.image.url)

        # Update quantity above threshold
        resp = self.client.post(reverse('stock_edit', args=[prod.pk]), {
            'name': 'Filet de boeuf',
            'category': StockProduct.VIANDE,
            'quantity': '12.00',
            'unit': 'kg',
            'threshold': '5.00',
        })
        self.assertRedirects(resp, reverse('stock_list'))
        prod.refresh_from_db()
        self.assertFalse(prod.is_low)
        self.assertTrue(bool(prod.image))  # image conservée si non remplacée

        # Oversized image rejected
        huge = SimpleUploadedFile('huge.png', b'0' * (6 * 1024 * 1024), content_type='image/png')
        bad = self.client.post(reverse('stock_add'), {
            'name': 'Pommes de terre',
            'category': StockProduct.LEGUMES,
            'quantity': '10',
            'unit': 'kg',
            'threshold': '2',
            'image': huge,
        })
        self.assertEqual(bad.status_code, 200)
        self.assertFalse(StockProduct.objects.filter(name='Pommes de terre').exists())

        # Delete
        resp = self.client.post(reverse('stock_delete', args=[prod.pk]))
        self.assertRedirects(resp, reverse('stock_list'))
        self.assertFalse(StockProduct.objects.filter(pk=prod.pk).exists())
