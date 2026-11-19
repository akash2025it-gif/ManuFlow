"""
Django settings for nit_system (NIT Trichy Order-to-Audit Management System).
"""

import os
import sys
from pathlib import Path

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

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-nit-trichy-order-to-audit-foundation-key-2026'
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'True').lower() in ('true', '1', 't', 'yes')

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    if host.strip()
]

# CSRF Trusted Origins (for cloud hosting like Render, Railway, Heroku)
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',')
    if origin.strip()
]

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
USE_SQLITE = os.environ.get('USE_SQLITE', 'True').lower() in ('true', '1', 't', 'yes')

if DATABASE_URL:
    try:
        import dj_database_url
        DATABASES = {'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600)}
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
            DATABASES = {
                'default': {
                    'ENGINE': db_engine,
                    'NAME': parsed_db.path.lstrip('/'),
                    'USER': urllib.parse.unquote(parsed_db.username or ''),
                    'PASSWORD': urllib.parse.unquote(parsed_db.password or ''),
                    'HOST': parsed_db.hostname or 'localhost',
                    'PORT': str(parsed_db.port) if parsed_db.port else default_port,
                    'CONN_MAX_AGE': 600,
                }
            }
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
