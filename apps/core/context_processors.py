from datetime import datetime


def system_context(request):
    """
    Exposes global NIT Trichy Order-to-Audit context variables to all templates.
    """
    return {
        'SYSTEM_NAME': 'NIT Trichy Order-to-Audit System',
        'SYSTEM_SHORT_NAME': 'NIT O2A',
        'INSTITUTION_NAME': 'National Institute of Technology, Tiruchirappalli',
        'CURRENT_YEAR': datetime.now().year,
        'SYSTEM_VERSION': 'v1.0.0-foundation',
    }
