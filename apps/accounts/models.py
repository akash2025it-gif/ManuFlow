from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class CustomUserManager(BaseUserManager):
    """
    Custom user manager where email is the unique identifier for authentication.
    """
    def create_user(self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        if not username:
            raise ValueError('The Username field must be set')

        email = self.normalize_email(email)
        user = self.model(email=email, username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', CustomUser.Role.ADMIN)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, username, password, **extra_fields)


class CustomUser(AbstractUser):
    """
    Custom user model for the NIT Trichy Order-to-Audit Management System.
    Includes strict role-based access for:
    - Admin
    - Salesman
    - Production
    - Auditor
    - Owner
    """

    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Administrator'
        SALESMAN = 'SALESMAN', 'Salesman'
        PRODUCTION = 'PRODUCTION', 'Production'
        AUDITOR = 'AUDITOR', 'Auditor'
        OWNER = 'OWNER', 'Owner'
        ACCOUNTANT = 'ACCOUNTANT', 'Accountant'

    email = models.EmailField('Email Address', unique=True)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.SALESMAN,
        help_text='Designated role for workflow permissions and dashboard access.'
    )
    employee_id = models.CharField(
        'Employee ID',
        max_length=30,
        unique=True,
        blank=True,
        null=True,
        help_text='Unique NIT Trichy Staff/Employee ID (e.g. NIT-1001)'
    )
    department = models.CharField('Department', max_length=100, blank=True, default='')
    phone_number = models.CharField('Phone Number', max_length=20, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-date_joined']

    def __str__(self):
        full = self.get_full_name()
        display_name = full if full else self.username
        return f"{display_name} [{self.get_role_display()}]"

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_salesman(self):
        return self.role == self.Role.SALESMAN

    @property
    def is_production(self):
        return self.role == self.Role.PRODUCTION

    @property
    def is_auditor(self):
        return self.role == self.Role.AUDITOR

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER

    @property
    def is_accountant(self):
        return self.role == self.Role.ACCOUNTANT

    def get_dashboard_name(self):
        """Returns the URL name of the user's dashboard based on their role."""
        if self.is_admin:
            return 'admin_dashboard'
        elif self.role == self.Role.SALESMAN:
            return 'salesman_dashboard'
        elif self.role == self.Role.PRODUCTION:
            return 'production_dashboard'
        elif self.role == self.Role.AUDITOR:
            return 'auditor_dashboard'
        elif self.role == self.Role.OWNER:
            return 'owner_dashboard'
        elif self.role == self.Role.ACCOUNTANT:
            return 'finance_dashboard'
        return 'login'
