from django.contrib.auth import get_user_model
from apps.accounts.models import CustomUser

DEMO_USER_CONFIG = {
    CustomUser.Role.ADMIN: {
        'email': 'admin@nit.edu',
        'username': 'admin',
        'first_name': 'NIT',
        'last_name': 'Administrator',
        'employee_id': 'NIT-ADM-001',
        'department': 'Systems & IT Administration',
        'is_staff': True,
        'is_superuser': True,
    },
    CustomUser.Role.SALESMAN: {
        'email': 'salesman@nit.edu',
        'username': 'salesman',
        'first_name': 'Ramesh',
        'last_name': 'Kumar',
        'employee_id': 'NIT-SLS-101',
        'department': 'Sales & Order Ingestion',
        'is_staff': False,
        'is_superuser': False,
    },
    CustomUser.Role.PRODUCTION: {
        'email': 'production@nit.edu',
        'username': 'production',
        'first_name': 'Suresh',
        'last_name': 'Production',
        'employee_id': 'NIT-PRD-201',
        'department': 'Manufacturing Operations',
        'is_staff': False,
        'is_superuser': False,
    },
    CustomUser.Role.ACCOUNTANT: {
        'email': 'accountant@nit.edu',
        'username': 'accountant',
        'first_name': 'Anand',
        'last_name': 'Accountant',
        'employee_id': 'NIT-ACT-301',
        'department': 'Finance & Accounting',
        'is_staff': False,
        'is_superuser': False,
    },
    CustomUser.Role.AUDITOR: {
        'email': 'auditor@nit.edu',
        'username': 'auditor',
        'first_name': 'Lakshmi',
        'last_name': 'Auditor',
        'employee_id': 'NIT-AUD-401',
        'department': 'Internal Audit & Compliance',
        'is_staff': False,
        'is_superuser': False,
    },
    CustomUser.Role.OWNER: {
        'email': 'demo@manuflow.app',
        'username': 'demo_user',
        'first_name': 'Executive',
        'last_name': 'Demonstration',
        'employee_id': 'MF-DEMO-001',
        'department': 'Executive Operations',
        'is_staff': False,
        'is_superuser': False,
    },
}

DEFAULT_DEMO_PASSWORD = 'ManuFlow@Demo2026!'


def get_or_create_demo_user(role, password=None):
    """
    Idempotently retrieves or creates a valid, active CustomUser for the requested role.
    Guarantees non-null foreign key integrity across both local SQLite and production PostgreSQL.
    """
    UserModel = get_user_model()
    pwd = password or DEFAULT_DEMO_PASSWORD

    # 1. Search for an existing active user holding this role
    user = UserModel.objects.filter(role=role, is_active=True).first()
    if user:
        return user

    cfg = DEMO_USER_CONFIG.get(role, {})
    email = cfg.get('email', f"{role.lower()}@nit.edu")
    username = cfg.get('username', role.lower())

    # 2. Check if user exists by email
    user = UserModel.objects.filter(email__iexact=email).first()
    if not user:
        # 3. Check if user exists by username
        user = UserModel.objects.filter(username__iexact=username).first()

    if user:
        updated_fields = []
        if user.role != role:
            user.role = role
            updated_fields.append('role')
        if not user.is_active:
            user.is_active = True
            updated_fields.append('is_active')
        if cfg.get('is_staff') and not user.is_staff:
            user.is_staff = True
            updated_fields.append('is_staff')
        if cfg.get('is_superuser') and not user.is_superuser:
            user.is_superuser = True
            updated_fields.append('is_superuser')
        if updated_fields:
            user.save(update_fields=updated_fields)
        return user

    # 4. Create new user safely
    is_super = cfg.get('is_superuser', False) or (role == CustomUser.Role.ADMIN)
    if is_super:
        user = UserModel.objects.create_superuser(
            email=email,
            username=username,
            password=pwd,
            first_name=cfg.get('first_name', 'NIT'),
            last_name=cfg.get('last_name', 'Administrator'),
            employee_id=cfg.get('employee_id', 'NIT-ADM-001'),
            department=cfg.get('department', 'Administration'),
        )
    else:
        user = UserModel.objects.create_user(
            email=email,
            username=username,
            password=pwd,
            role=role,
            first_name=cfg.get('first_name', role.title()),
            last_name=cfg.get('last_name', 'Staff'),
            employee_id=cfg.get('employee_id', f"NIT-{role[:3]}-001"),
            department=cfg.get('department', 'Operations'),
            is_active=True,
            is_staff=cfg.get('is_staff', False),
            is_superuser=False,
        )
    return user


def ensure_all_demo_users_exist(password=None):
    """
    Ensures that active demo accounts for all 6 operational roles exist in the database.
    """
    users = {}
    for role in DEMO_USER_CONFIG.keys():
        users[role] = get_or_create_demo_user(role, password=password)
    return users
