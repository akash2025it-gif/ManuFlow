from datetime import datetime
from django.conf import settings


def system_context(request):
    """
    Exposes global ManuFlow context variables to all templates.
    """
    return {
        'SYSTEM_NAME': 'ManuFlow',
        'SYSTEM_SHORT_NAME': 'ManuFlow',
        'SYSTEM_SUBTITLE': 'Manufacturing & Order Management System',
        'DEFAULT_BROWSER_TITLE': 'ManuFlow | Manufacturing ERP',
        'INSTITUTION_NAME': 'ManuFlow Platform',
        'CURRENT_YEAR': datetime.now().year,
        'SYSTEM_VERSION': 'v1.0.0',
        'DEMO_MODE': getattr(settings, 'DEMO_MODE', settings.DEBUG),
        'DEBUG': settings.DEBUG,
    }
