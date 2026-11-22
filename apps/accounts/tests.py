from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import CustomUser


class CustomUserModelTests(TestCase):
    def test_create_user(self):
        user = CustomUser.objects.create_user(
            email='testuser@nit.edu',
            username='testuser',
            password='TestPassword123',
            role=CustomUser.Role.SALESMAN,
            employee_id='NIT-TEST-01'
        )
        self.assertEqual(user.email, 'testuser@nit.edu')
        self.assertEqual(user.username, 'testuser')
        self.assertEqual(user.role, CustomUser.Role.SALESMAN)
        self.assertTrue(user.is_salesman)
        self.assertFalse(user.is_admin)
        self.assertTrue(user.check_password('TestPassword123'))
        self.assertEqual(user.get_dashboard_name(), 'salesman_dashboard')

    def test_create_superuser(self):
        admin = CustomUser.objects.create_superuser(
            email='admin@nit.edu',
            username='admin',
            password='AdminPassword123'
        )
        self.assertEqual(admin.role, CustomUser.Role.ADMIN)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_admin)
        self.assertEqual(admin.get_dashboard_name(), 'admin_dashboard')


class AuthenticationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = 'SecretPass123'
        self.user = CustomUser.objects.create_user(
            email='salesman@nit.edu',
            username='salesuser',
            password=self.password,
            role=CustomUser.Role.SALESMAN
        )

    def test_login_with_email(self):
        response = self.client.post(reverse('login'), {
            'username': 'salesman@nit.edu',
            'password': self.password,
        })
        self.assertRedirects(response, reverse('salesman_dashboard'))

    def test_login_with_username(self):
        response = self.client.post(reverse('login'), {
            'username': 'salesuser',
            'password': self.password,
        })
        self.assertRedirects(response, reverse('salesman_dashboard'))

    def test_login_invalid_credentials(self):
        response = self.client.post(reverse('login'), {
            'username': 'salesman@nit.edu',
            'password': 'WrongPassword!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context['form'],
            None,
            "Invalid login credentials. Please check your email/username and password."
        )

    def test_logout(self):
        self.client.login(username='salesuser', password=self.password)
        response = self.client.post(reverse('logout'))
        self.assertRedirects(response, reverse('login'))

    def test_logout_rejects_get_requests(self):
        """Logout is state-changing and must retain Django's CSRF protection."""
        self.client.login(username='salesuser', password=self.password)
        response = self.client.get(reverse('logout'))
        self.assertEqual(response.status_code, 405)


class RoleBasedAccessTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = 'UniversalPass123'
        self.admin = CustomUser.objects.create_user(
            email='admin@nit.edu', username='admin_u', password=self.password,
            role=CustomUser.Role.ADMIN, is_staff=True
        )
        self.salesman = CustomUser.objects.create_user(
            email='sales@nit.edu', username='sales_u', password=self.password,
            role=CustomUser.Role.SALESMAN
        )
        self.production = CustomUser.objects.create_user(
            email='prod@nit.edu', username='prod_u', password=self.password,
            role=CustomUser.Role.PRODUCTION
        )
        self.auditor = CustomUser.objects.create_user(
            email='audit@nit.edu', username='audit_u', password=self.password,
            role=CustomUser.Role.AUDITOR
        )
        self.owner = CustomUser.objects.create_user(
            email='owner@nit.edu', username='owner_u', password=self.password,
            role=CustomUser.Role.OWNER
        )

    def test_unauthenticated_redirect(self):
        response = self.client.get(reverse('dashboard_home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_dispatcher_redirections(self):
        # Admin dispatcher
        self.client.login(username='admin_u', password=self.password)
        res = self.client.get(reverse('dashboard_home'))
        self.assertRedirects(res, reverse('admin_dashboard'))
        self.client.logout()

        # Salesman dispatcher
        self.client.login(username='sales_u', password=self.password)
        res = self.client.get(reverse('dashboard_home'))
        self.assertRedirects(res, reverse('salesman_dashboard'))
        self.client.logout()

        # Production dispatcher
        self.client.login(username='prod_u', password=self.password)
        res = self.client.get(reverse('dashboard_home'))
        self.assertRedirects(res, reverse('production_dashboard'))
        self.client.logout()

        # Auditor dispatcher
        self.client.login(username='audit_u', password=self.password)
        res = self.client.get(reverse('dashboard_home'))
        self.assertRedirects(res, reverse('auditor_dashboard'))
        self.client.logout()

        # Owner dispatcher
        self.client.login(username='owner_u', password=self.password)
        res = self.client.get(reverse('dashboard_home'))
        self.assertRedirects(res, reverse('owner_dashboard'))
        self.client.logout()

    def test_authorized_dashboard_access(self):
        # Test each role can access their own dashboard
        self.client.login(username='admin_u', password=self.password)
        self.assertEqual(self.client.get(reverse('admin_dashboard')).status_code, 200)
        self.client.logout()

        self.client.login(username='sales_u', password=self.password)
        self.assertEqual(self.client.get(reverse('salesman_dashboard')).status_code, 200)
        self.client.logout()

        self.client.login(username='prod_u', password=self.password)
        self.assertEqual(self.client.get(reverse('production_dashboard')).status_code, 200)
        self.client.logout()

        self.client.login(username='audit_u', password=self.password)
        self.assertEqual(self.client.get(reverse('auditor_dashboard')).status_code, 200)
        self.client.logout()

        self.client.login(username='owner_u', password=self.password)
        self.assertEqual(self.client.get(reverse('owner_dashboard')).status_code, 200)
        self.client.logout()

    def test_unauthorized_dashboard_access_returns_403(self):
        # Salesman trying to access Admin dashboard -> 403
        self.client.login(username='sales_u', password=self.password)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 403)

        # Salesman trying to access Production dashboard -> 403
        response = self.client.get(reverse('production_dashboard'))
        self.assertEqual(response.status_code, 403)

        # Auditor trying to access Sales dashboard -> 403
        self.client.logout()
        self.client.login(username='audit_u', password=self.password)
        response = self.client.get(reverse('salesman_dashboard'))
        self.assertEqual(response.status_code, 403)

        # Production trying to access Owner dashboard -> 403
        self.client.logout()
        self.client.login(username='prod_u', password=self.password)
        response = self.client.get(reverse('owner_dashboard'))
        self.assertEqual(response.status_code, 403)
