from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from apps.accounts.models import CustomUser


class Command(BaseCommand):
    help = 'Seeds initial test accounts for all Order-to-Audit roles'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force-production',
            action='store_true',
            help='Allow running seed_users in production with a custom secure password'
        )
        parser.add_argument(
            '--password',
            type=str,
            default=None,
            help='Specify a secure custom password instead of default demo password'
        )

    def handle(self, *args, **options):
        is_demo_mode = getattr(settings, 'DEMO_MODE', settings.DEBUG)
        custom_password = options.get('password')
        force_production = options.get('force_production', False)

        if not is_demo_mode and not force_production:
            raise CommandError(
                "CRITICAL SECURITY GUARD: 'seed_users' with default demo password (nit@12345) "
                "is strictly prohibited in production! To seed users in production, provide "
                "--force-production and --password=<secure_password>."
            )

        default_pwd = custom_password or 'nit@12345'

        users_data = [
            {
                'email': 'admin@nit.edu',
                'username': 'admin',
                'password': default_pwd,
                'role': CustomUser.Role.ADMIN,
                'first_name': 'System',
                'last_name': 'Administrator',
                'employee_id': 'MF-ADM-001',
                'department': 'Systems & IT Administration',
                'is_staff': True,
                'is_superuser': True,
            },
            {
                'email': 'salesman@nit.edu',
                'username': 'salesman',
                'password': default_pwd,
                'role': CustomUser.Role.SALESMAN,
                'first_name': 'Ramesh',
                'last_name': 'Kumar',
                'employee_id': 'NIT-SLS-101',
                'department': 'Sales & Order Ingestion',
                'is_staff': False,
                'is_superuser': False,
            },
            {
                'email': 'production@nit.edu',
                'username': 'production',
                'password': default_pwd,
                'role': CustomUser.Role.PRODUCTION,
                'first_name': 'Karthik',
                'last_name': 'Natarajan',
                'employee_id': 'NIT-PRD-201',
                'department': 'Shop Floor & Manufacturing',
                'is_staff': False,
                'is_superuser': False,
            },
            {
                'email': 'auditor@nit.edu',
                'username': 'auditor',
                'password': default_pwd,
                'role': CustomUser.Role.AUDITOR,
                'first_name': 'Deepa',
                'last_name': 'Sundaram',
                'employee_id': 'NIT-AUD-301',
                'department': 'Internal Audit & Governance',
                'is_staff': False,
                'is_superuser': False,
            },
            {
                'email': 'owner@nit.edu',
                'username': 'owner',
                'password': default_pwd,
                'role': CustomUser.Role.OWNER,
                'first_name': 'Dr. S.',
                'last_name': 'Venkatesh',
                'employee_id': 'NIT-OWN-001',
                'department': 'Executive Directorate',
                'is_staff': False,
                'is_superuser': False,
            },
            {
                'email': 'accountant@nit.edu',
                'username': 'accountant',
                'password': default_pwd,
                'role': CustomUser.Role.ACCOUNTANT,
                'first_name': 'Anand',
                'last_name': 'Subramanian',
                'employee_id': 'NIT-ACC-401',
                'department': 'Finance & Commercial Accounts',
                'is_staff': False,
                'is_superuser': False,
            },
        ]

        created_count = 0
        updated_count = 0

        for data in users_data:
            password = data.pop('password')
            email = data['email']
            user, created = CustomUser.objects.get_or_create(email=email, defaults=data)
            user.set_password(password)
            for key, val in data.items():
                setattr(user, key, val)
            user.save()

            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created {user.role}: {user.email} (Username: {user.username})"))
            else:
                updated_count += 1
                self.stdout.write(self.style.WARNING(f"Updated {user.role}: {user.email} (Username: {user.username})"))

        self.stdout.write(self.style.SUCCESS(
            f"Successfully seeded users! Created: {created_count}, Updated: {updated_count}. Password for all: nit@12345"
        ))
