from datetime import datetime
from django.conf import settings


def system_context(request):
    """
    Exposes global ManuFlow context variables to all templates.
    Dynamically resolves real database engine and environment mode.
    """
    db_engine_raw = settings.DATABASES['default']['ENGINE'].split('.')[-1].lower()
    if 'postgres' in db_engine_raw:
        db_badge = 'PostgreSQL'
    elif 'sqlite' in db_engine_raw:
        db_badge = 'SQLite'
    elif 'mysql' in db_engine_raw:
        db_badge = 'MySQL'
    else:
        db_badge = db_engine_raw.upper()

    env_label = 'Production' if not settings.DEBUG else 'Development'

    return {
        'SYSTEM_NAME': 'ManuFlow',
        'SYSTEM_SHORT_NAME': 'ManuFlow',
        'SYSTEM_SUBTITLE': 'Manufacturing & Order Management System',
        'DEFAULT_BROWSER_TITLE': 'ManuFlow | Manufacturing ERP',
        'INSTITUTION_NAME': 'ManuFlow Platform',
        'CURRENT_YEAR': datetime.now().year,
        'SYSTEM_VERSION': 'v1.0.0',
        'DEMO_MODE': getattr(settings, 'DEMO_MODE', False),
        'DEBUG': settings.DEBUG,
        'DB_BADGE': db_badge,
        'ENV_LABEL': env_label,
        'SYSTEM_STATUS': f"{db_badge} / {env_label}",
    }
