from django.db import migrations
from django.contrib.auth.hashers import make_password


def seed_demo_account(apps, schema_editor):
    CustomUser = apps.get_model('accounts', 'CustomUser')
    email = 'demo@manuflow.app'
    username = 'demo_user'
    default_pwd = 'ManuFlow@Demo2026!'

    user = CustomUser.objects.filter(email__iexact=email).first()
    if not user:
        user = CustomUser.objects.filter(username__iexact=username).first()

    if not user:
        CustomUser.objects.create(
            email=email,
            username=username,
            password=make_password(default_pwd),
            role='OWNER',
            first_name='Executive',
            last_name='Demonstration',
            employee_id='MF-DEMO-001',
            department='Executive Operations',
            phone_number='+91 98765 43210',
            is_active=True,
            is_staff=False,
            is_superuser=False,
        )
    else:
        user.role = 'OWNER'
        user.is_active = True
        user.is_staff = False
        user.is_superuser = False
        user.password = make_password(default_pwd)
        user.save()


def remove_demo_account(apps, schema_editor):
    CustomUser = apps.get_model('accounts', 'CustomUser')
    CustomUser.objects.filter(email='demo@manuflow.app').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_alter_customuser_role'),
    ]

    operations = [
        migrations.RunPython(seed_demo_account, remove_demo_account),
    ]
