"""Django settings for the Leyte Disaster Early Warning System portal."""
import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Security --------------------------------------------------------------
# In production set DJANGO_SECRET_KEY and DJANGO_DEBUG=0 via environment.
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY', 'dev-insecure-key-change-me-in-production'
)
DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
# Allow managed PaaS hosts (Render production + preview subdomains, Vercel).
ALLOWED_HOSTS += ['.onrender.com', '.vercel.app']
# Render injects the public hostname at runtime — trust it automatically.
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# HTTPS origins trusted for unsafe (POST) requests — required for the login form
# and any browser POST when served over HTTPS (Django 4+ CSRF origin check).
CSRF_TRUSTED_ORIGINS = ['https://*.onrender.com', 'https://*.vercel.app']
if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f'https://{RENDER_EXTERNAL_HOSTNAME}')

# --- Applications ----------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'axes',
    # Local
    'accounts',
    'core',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise serves collected static files in production; must sit directly
    # after SecurityMiddleware and before everything else.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # AxesMiddleware must be the last authentication-related middleware so it
    # can observe the outcome of each login attempt.
    'axes.middleware.AxesMiddleware',
]

ROOT_URLCONF = 'dews_portal.urls'

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
            ],
        },
    },
]

WSGI_APPLICATION = 'dews_portal.wsgi.application'

# --- Database --------------------------------------------------------------
# Uses DATABASE_URL when present (Render Postgres); falls back to local SQLite.
import dj_database_url  # noqa: E402

DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}',
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# --- Custom user -----------------------------------------------------------
AUTH_USER_MODEL = 'accounts.User'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'manage-dashboard'
LOGOUT_REDIRECT_URL = 'login'

# Authentication backends. AxesStandaloneBackend MUST be first so brute-force
# lockouts are enforced before credentials are ever checked.
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- i18n / tz -------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Manila'
USE_I18N = True
USE_TZ = True

# --- Static & media --------------------------------------------------------
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# WhiteNoise: compress + hash static files for cache-busting in production.
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Production security ----------------------------------------------------
# Enabled automatically whenever DEBUG is off (i.e. on Render / any real host).
if not DEBUG:
    # Render terminates TLS at its proxy and forwards this header.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SECURE_SSL_REDIRECT', '1') == '1'
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_HSTS_SECONDS', 0))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# --- Django REST Framework -------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
    ),
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.ScopedRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'login': '10/min',
        'public': '120/min',
    },
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 100,
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
}

# --- CORS ------------------------------------------------------------------
# The masked public API is meant to be reachable by mobile clients.
CORS_ALLOWED_ORIGIN_REGEXES = [r'.*']
CORS_URLS_REGEX = r'^/api/public/.*$'

# Public API keys (comma separated). Leave blank to allow open read access.
PUBLIC_API_KEYS = [
    k.strip() for k in os.environ.get('PUBLIC_API_KEYS', '').split(',') if k.strip()
]

# --- django-axes (active brute-force defense) ------------------------------
# Disabled in local development (DEBUG) so repeated test logins don't lock you
# out; always on in production. Override explicitly with DJANGO_AXES_ENABLED.
AXES_ENABLED = os.environ.get('DJANGO_AXES_ENABLED', '0' if DEBUG else '1') == '1'
# Lock after this many failed attempts...
AXES_FAILURE_LIMIT = int(os.environ.get('AXES_FAILURE_LIMIT', 5))
# ...counted per (username + IP) combination.
AXES_LOCKOUT_PARAMETERS = [['username', 'ip_address']]
# Automatic cool-off before a locked account/IP can try again.
AXES_COOLOFF_TIME = timedelta(minutes=15)
# A successful login clears the failure counter.
AXES_RESET_ON_SUCCESS = True
# Return a clean 429 rather than the default lockout template.
AXES_LOCKOUT_CALLABLE = 'core.axes_handlers.lockout_response'
AXES_CLIENT_IP_CALLABLE = None
# Admins can reset locks from the command line:
#   python manage.py axes_reset                     (all)
#   python manage.py axes_reset_username <username>
#   python manage.py axes_reset_ip <ip>
