import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from django.utils.translation import gettext_lazy as _

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-fallback-key-for-dev-only')
DEBUG = os.getenv("DJANGO_DEBUG", "False").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

ALLOWED_HOSTS = [
    "rafs.app",
    "www.rafs.app",
    "localhost",
    "127.0.0.1",
]

CSRF_TRUSTED_ORIGINS = [
    "https://rafs.app",
    "https://www.rafs.app",
]

SESSION_COOKIE_AGE = 60 * 60 * 24 * 365
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") 

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

if DEBUG or "test" in sys.argv:
    STORAGES["staticfiles"]["BACKEND"] = (
        "django.contrib.staticfiles.storage.StaticFilesStorage"
    )

WHITENOISE_AUTOREFRESH = DEBUG
WHITENOISE_USE_FINDERS = DEBUG

# Application definition

INSTALLED_APPS = [
    # Built-in Django apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.contrib.postgres',
    'django.contrib.sitemaps',

    # Third-party apps
    'parler',
    'rest_framework',
    'taggit',

    # Local / project apps
    'accounts',
    'movies',
    'core',
    'feedback',
    'notifications',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
LOGIN_URL = 'login'

LOGIN_REDIRECT_URL = '/'

LOGOUT_REDIRECT_URL = '/'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.site_event',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Seasonal appearance switch, e.g. SITE_EVENT=halloween-2026. Empty means the
# ordinary site: event-only markup (and therefore its images) is not rendered.
SITE_EVENT = os.getenv("SITE_EVENT", "").strip()


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DB_ENGINE = os.getenv("DB_ENGINE", "sqlite").lower()

if DB_ENGINE == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "rafs_dev"),
            "USER": os.getenv("DB_USER", "rafs_user"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/
LANGUAGE_CODE = 'en'
TIME_ZONE = 'Asia/Almaty'
USE_I18N = True
USE_TZ = True
LANGUAGES = [
    ("en", _("English")),
    ("ru", _("Russian")),
    ("uk", _("Ukrainian")),
    ("kk", _("Kazakh")),
    ("es", _("Spanish")),
    ("de", _("German")),
]

LOCALE_PATHS = [
    BASE_DIR / 'locale'
]

# Parler
PARLER_DEFAULT_LANGUAGE_CODE = "en"
PARLER_LANGUAGES = {
    None: (
        {"code": "en"},
        {"code": "ru"},
        {"code": "uk"},
        {"code": "kk"},
        {"code": "es"},
        {"code": "de"}
    ),
    "default": {
        "fallbacks": ["en", "ru"],
        "hide_untranslated": False,
    },
}

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

STATICFILES_DIRS = [
    BASE_DIR / "static"
]

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
    'DEFAULT_THROTTLE_RATES': {"feedback": "5/hour"},
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25
}

AUTH_USER_MODEL = "accounts.User"

# Celery config
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "")

# Email: Resend SMTP. The key lives only in .env (API_RESEND).
# Console by default: this server is also production, so real sending is switched on
# from .env (EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend), not in code.
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = "smtp.resend.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = "resend"
EMAIL_HOST_PASSWORD = os.getenv("API_RESEND", "")
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = "RAFS <noreply@rafs.app>"
FEEDBACK_EMAIL = "hello@rafs.app"
