from django.test import TestCase
from django.urls import reverse

from .models import CustomUser


class AccountAjaxTests(TestCase):
    def setUp(self):
        CustomUser.objects.create_user('alice', password='s3cret-pass')

    def test_anonymous_page_shows_login_form(self):
        r = self.client.get(reverse('account:account'))
        self.assertContains(r, 'id="login-form"')

    def test_login_valid_and_logged_page(self):
        r = self.client.post(reverse('account:login'),
                             {'username': 'alice', 'password': 's3cret-pass'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('Logged as alice', r.json()['html'])
        r = self.client.get(reverse('account:account'))
        self.assertContains(r, 'Logged as alice')

    def test_login_invalid_returns_errors(self):
        r = self.client.post(reverse('account:login'),
                             {'username': 'alice', 'password': 'bad'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('__all__', r.json()['errors'])

    def test_logout_post_only(self):
        self.client.login(username='alice', password='s3cret-pass')
        self.assertEqual(self.client.get(reverse('account:logout')).status_code, 405)
        r = self.client.post(reverse('account:logout'))
        self.assertIn('login-form', r.json()['html'])

    def test_csrf_rotation_login_logout_login(self):
        """Regression: login -> logout -> login with the *current* cookie token."""
        from django.test import Client
        c = Client(enforce_csrf_checks=True)

        def token():
            return c.cookies['csrftoken'].value

        c.get(reverse('account:account'))
        creds = {'username': 'alice', 'password': 's3cret-pass'}
        r = c.post(reverse('account:login'), creds, HTTP_X_CSRFTOKEN=token())
        self.assertEqual(r.status_code, 200)
        r = c.post(reverse('account:logout'), HTTP_X_CSRFTOKEN=token())
        self.assertEqual(r.status_code, 200)
        r = c.post(reverse('account:login'), creds, HTTP_X_CSRFTOKEN=token())
        self.assertEqual(r.status_code, 200)
