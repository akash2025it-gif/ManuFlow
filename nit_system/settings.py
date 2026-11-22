"""
Django settings for nit_system (NIT Trichy Order-to-Audit Management System).
"""

import os
import sys
from pathlib import Path
from django.core.management.utils import get_random_secret_key

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Add apps directory to sys.path
sys.path.insert(0, str(BASE_DIR / 'apps'))

# Load environment variables from .env if present
env_file = BASE_DIR / '.env'
if env_file.exists():
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ.setdefault(key.strip(), val.strip().strip("'\""))

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'True').lower() in ('true', '1', 't', 'yes')

# A deployment must provide its own persistent key.  Local development remains
# zero-configuration, while avoiding a committed fallback that could otherwise
# be accidentally used to sign production sessions and CSRF tokens.
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured('SECRET_KEY environment variable is mandatory when DEBUG=False.')
    SECRET_KEY = get_random_secret_key()

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver,.onrender.com').split(',')
    if host.strip()
]

# CSRF Trusted Origins (for cloud hosting like Render, Railway, Heroku)
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',')
    if origin.strip()
]

# Render Cloud Hosting integration (automatic hostname & HTTPS CSRF origin resolution)
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    if RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    render_origin = f'https://{RENDER_EXTERNAL_HOSTNAME}'
    if render_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(render_origin)

# Academic Demo Mode Configuration
# Defaults to False. Only active during local development when DEBUG=True.
# In production (DEBUG=False), demo mode and 1-click demo logins are hard-disabled.
DEMO_MODE = (
    DEBUG and os.environ.get('DEMO_MODE', 'True').lower() in ('true', '1', 't', 'yes')
) if DEBUG else False

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Custom Project Apps
    'apps.accounts.apps.AccountsConfig',
    'apps.core.apps.CoreConfig',
    'apps.dashboard.apps.DashboardConfig',
    'apps.master_data.apps.MasterDataConfig',
    'apps.inventory.apps.InventoryConfig',
    'apps.production.apps.ProductionConfig',
    'apps.sales.apps.SalesConfig',
    'apps.finance.apps.FinanceConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'nit_system.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.system_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'nit_system.wsgi.application'
ASGI_APPLICATION = 'nit_system.asgi.application'

# Database Configuration
# Supports DATABASE_URL (12-Factor app pattern for Render/Railway/Heroku),
# individual DB_* environment variables, or SQLite fallback for local development.
import urllib.parse

DATABASE_URL = os.environ.get('DATABASE_URL')

# Production Database Integrity Guard:
# In production (DEBUG=False), DATABASE_URL is strictly mandatory to prevent silent SQLite
# fallback on ephemeral container filesystems (e.g. Render Free Web Services).
if not DEBUG and not DATABASE_URL:
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured(
        "DATABASE_URL environment variable is mandatory in production (DEBUG=False). "
        "SQLite cannot be used as a production database on ephemeral cloud hosting."
    )

USE_SQLITE = os.environ.get('USE_SQLITE', str(DEBUG)).lower() in ('true', '1', 't', 'yes')

if DATABASE_URL:
    try:
        import dj_database_url
        DATABASES = {'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600, conn_health_checks=True)}
    except ImportError:
        parsed_db = urllib.parse.urlparse(DATABASE_URL)
        if parsed_db.scheme in ('postgres', 'postgresql', 'pgsql'):
            db_engine = 'django.db.backends.postgresql'
            default_port = '5432'
        elif parsed_db.scheme == 'sqlite':
            db_engine = 'django.db.backends.sqlite3'
            default_port = ''
        else:
            db_engine = 'django.db.backends.postgresql'
            default_port = '5432'

        if db_engine == 'django.db.backends.sqlite3':
            DATABASES = {
                'default': {
                    'ENGINE': db_engine,
                    'NAME': parsed_db.path.lstrip('/') or str(BASE_DIR / 'db.sqlite3'),
                }
            }
        else:
            db_options = {}
            if 'sslmode=' in parsed_db.query or 'neon.tech' in (parsed_db.hostname or ''):
                db_options['sslmode'] = 'require'

            DATABASES = {
                'default': {
                    'ENGINE': db_engine,
                    'NAME': parsed_db.path.lstrip('/'),
                    'USER': urllib.parse.unquote(parsed_db.username or ''),
                    'PASSWORD': urllib.parse.unquote(parsed_db.password or ''),
                    'HOST': parsed_db.hostname or 'localhost',
                    'PORT': str(parsed_db.port) if parsed_db.port else default_port,
                    'CONN_MAX_AGE': 600,
                    'CONN_HEALTH_CHECKS': True,
                    'OPTIONS': db_options,
                }
            }

    # Neon Serverless PostgreSQL & Cloud SSL Compatibility Guard
    DATABASES['default'].setdefault('CONN_HEALTH_CHECKS', True)
    if 'sslmode=require' in DATABASE_URL or 'neon.tech' in DATABASE_URL:
        DATABASES['default'].setdefault('OPTIONS', {})['sslmode'] = 'require'
elif USE_SQLITE:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': os.environ.get('DB_ENGINE', 'django.db.backends.postgresql'),
            'NAME': os.environ.get('DB_NAME', 'nit_ordertoaudit_db'),
            'USER': os.environ.get('DB_USER', 'postgres'),
            'PASSWORD': os.environ.get('DB_PASSWORD', 'postgres'),
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '5432'),
            'CONN_MAX_AGE': 600,
        }
    }

# Custom User Model
AUTH_USER_MODEL = 'accounts.CustomUser'

# Authentication Backends (supports email and username login)
AUTHENTICATION_BACKENDS = [
    'apps.accounts.backends.EmailOrUsernameBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8},
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# WhiteNoise integration for high-performance static asset hosting in production
try:
    import whitenoise
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
except ImportError:
    pass

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Authentication URLs
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard_home'
LOGOUT_REDIRECT_URL = 'login'

# Security Headers & Cookie Configurations
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # Allows standard client-side CSRF handling if needed

# Production Security Configurations (active when DEBUG=False)
if not DEBUG:
    SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'True').lower() in ('true', '1', 't', 'yes')
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'True').lower() in ('true', '1', 't', 'yes')
    CSRF_COOKIE_SECURE = os.environ.get('CSRF_COOKIE_SECURE', 'True').lower() in ('true', '1', 't', 'yes')
    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
