import re

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import (ROLE_ADMIN, ROLE_CHEF, ROLE_CLEANER, ROLE_CLIENT, ROLE_RECEPTIONIST, User)

DOMAIN = {ROLE_CLIENT: 'booking.com', ROLE_ADMIN: 'admin.com'}


def make_user(role, n):
    return User.objects.create_user(
        email=f'u{n}@{DOMAIN.get(role, "service.com")}', password='OldPass#12345', role=role,
        cin=f'{10000000 + n}', nom='Ben', prenom='Test', telephone='20123456')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ForgotPasswordTests(TestCase):
    def send_code(self, user):
        r = self.client.post(reverse('reset_step1'), {'cin': user.cin, 'email': user.email})
        self.assertRedirects(r, reverse('reset_step2'))
        return re.search(r'\b(\d{6})\b', mail.outbox[-1].body).group(1)

    def test_full_flow_redirects_to_role_dashboard(self):
        for i, role in enumerate([ROLE_CLIENT, ROLE_ADMIN, ROLE_RECEPTIONIST, ROLE_CLEANER, ROLE_CHEF]):
            with self.subTest(role=role):
                self.client.logout()
                user = make_user(role, i)
                code = self.send_code(user)
                r = self.client.post(reverse('reset_step2'), {'code': code})
                self.assertRedirects(r, reverse('reset_step3'))
                r = self.client.post(reverse('reset_step3'),
                                     {'password1': 'NewPass#98765', 'password2': 'NewPass#98765'})
                self.assertRedirects(r, reverse('dashboard'), fetch_redirect_response=False)
                page = self.client.get(reverse('dashboard'))
                self.assertEqual(page.status_code, 200)
                self.assertEqual(page.context['user'].pk, user.pk)
                user.refresh_from_db()
                self.assertTrue(user.check_password('NewPass#98765'))

    def test_unknown_or_mismatched_cin_email(self):
        u = make_user(ROLE_CLIENT, 1)
        r = self.client.post(reverse('reset_step1'), {'cin': '99999999', 'email': u.email})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Aucun compte ne correspond')
        self.assertEqual(len(mail.outbox), 0)

    def test_wrong_code_blocks_step3(self):
        u = make_user(ROLE_CLIENT, 2)
        code = self.send_code(u)
        wrong = '000000' if code != '000000' else '111111'
        r = self.client.post(reverse('reset_step2'), {'code': wrong})
        self.assertContains(r, 'Code incorrect')
        self.assertRedirects(self.client.get(reverse('reset_step3')), reverse('reset_step2'))

    def test_too_many_attempts_resets_flow(self):
        u = make_user(ROLE_CLIENT, 3)
        code = self.send_code(u)
        wrong = '000000' if code != '000000' else '111111'
        for _ in range(6):
            self.client.post(reverse('reset_step2'), {'code': wrong})
        self.assertRedirects(self.client.get(reverse('reset_step2')), reverse('reset_step1'))

    def test_password_confirmation_must_match(self):
        u = make_user(ROLE_CLIENT, 4)
        self.client.post(reverse('reset_step2'), {'code': self.send_code(u)})
        r = self.client.post(reverse('reset_step3'),
                             {'password1': 'NewPass#98765', 'password2': 'Different#1'})
        self.assertContains(r, 'ne correspondent pas')
        u.refresh_from_db()
        self.assertTrue(u.check_password('OldPass#12345'))

    def test_steps_cannot_be_skipped(self):
        self.assertRedirects(self.client.get(reverse('reset_step2')), reverse('reset_step1'))
        self.assertRedirects(self.client.get(reverse('reset_step3')), reverse('reset_step1'))

    def test_inactive_user_rejected(self):
        u = make_user(ROLE_CLIENT, 5)
        u.is_active = False
        u.save()
        r = self.client.post(reverse('reset_step1'), {'cin': u.cin, 'email': u.email})
        self.assertContains(r, 'Aucun compte ne correspond')


class HomeTests(TestCase):
    def test_home_renders(self):
        r = self.client.get(reverse('home'))
        self.assertEqual(r.status_code, 200)
