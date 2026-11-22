from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.accounts.models import CustomUser


class Command(BaseCommand):
    help = 'Seeds or idempotently verifies the official ManuFlow demonstration account (demo@manuflow.app).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset-password',
            action='store_true',
            help='Force reset password to default demo password (ManuFlow@Demo2026!) even if already set.',
        )

    def handle(self, *args, **options):
        UserModel = get_user_model()
        email = 'demo@manuflow.app'
        username = 'demo_user'
        default_pwd = 'ManuFlow@Demo2026!'
        reset_pwd = options.get('reset_password', False)

        user = UserModel.objects.filter(email__iexact=email).first()
        if not user:
            user = UserModel.objects.filter(username__iexact=username).first()

        if not user:
            user = UserModel.objects.create_user(
                email=email,
                username=username,
                password=default_pwd,
                role=CustomUser.Role.OWNER,
                first_name='Executive',
                last_name='Demonstration',
                employee_id='MF-DEMO-001',
                department='Executive Operations',
                phone_number='+91 98765 43210',
                is_active=True,
                is_staff=False,
                is_superuser=False,
            )
            self.stdout.write(self.style.SUCCESS(
                f"Successfully created demo account: {user.email} (Username: {user.username}, Role: {user.get_role_display()})"
            ))
        else:
            updated_fields = []

            if user.email != email:
                user.email = email
                updated_fields.append('email')

            if user.role != CustomUser.Role.OWNER:
                user.role = CustomUser.Role.OWNER
                updated_fields.append('role')

            if not user.is_active:
                user.is_active = True
                updated_fields.append('is_active')

            # Strictly ensure demo account is not an administrator
            if user.is_staff or user.is_superuser:
                user.is_staff = False
                user.is_superuser = False
                updated_fields.extend(['is_staff', 'is_superuser'])

            # Verify and update password
            if not user.check_password(default_pwd) or reset_pwd:
                user.set_password(default_pwd)
                updated_fields.append('password')

            if updated_fields:
                user.save()
                self.stdout.write(self.style.SUCCESS(
                    f"Updated existing demo account: {user.email} (Fields: {', '.join(set(updated_fields))})"
                ))
            else:
                self.stdout.write(self.style.NOTICE(
                    f"Demo account is already up-to-date: {user.email} (Role: {user.get_role_display()})"
                ))

        self.stdout.write(self.style.SUCCESS("Demo credentials verified: demo@manuflow.app / ManuFlow@Demo2026!"))
