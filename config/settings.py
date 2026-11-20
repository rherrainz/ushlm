import os
from pathlib import Path
from urllib.parse import urlsplit, unquote, parse_qs
from django.core.exceptions import ImproperlyConfigured
BASE_DIR = Path(__file__).resolve().parent.parent
# Small dotenv reader: environment variables always take precedence.
if (BASE_DIR / '.env').exists():
    for line in (BASE_DIR / '.env').read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip())
DEBUG = os.getenv('DJANGO_DEBUG', '0') == '1'
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    raise ImproperlyConfigured('Definí DJANGO_SECRET_KEY en .env o en el entorno.')
ON_VERCEL = os.getenv('VERCEL') == '1'
if ON_VERCEL and DEBUG:
    raise ImproperlyConfigured('En Vercel, DJANGO_DEBUG debe ser 0.')
ALLOWED_HOSTS = [host.strip() for host in os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if host.strip()]
for name in ('VERCEL_URL', 'VERCEL_PROJECT_PRODUCTION_URL', 'VERCEL_BRANCH_URL'):
    host = os.getenv(name, '').strip()
    if host and host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(host)
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if origin.strip()]
if ON_VERCEL:
    # Vercel terminates TLS before forwarding the request to Django.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 3600
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

INSTALLED_APPS = ['django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'market']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'config.wsgi.application'
database_url = os.getenv('DATABASE_URL', '')
if ON_VERCEL and not database_url:
    raise ImproperlyConfigured('Configurá DATABASE_URL de Neon; SQLite no es persistente en Vercel.')
if database_url:
    url = urlsplit(database_url)
    if url.scheme not in ('postgres', 'postgresql') or not url.hostname or not url.path.strip('/'):
        raise ImproperlyConfigured('DATABASE_URL debe ser una URL PostgreSQL válida.')
    options = parse_qs(url.query)
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': unquote(url.path.lstrip('/')),
        'USER': unquote(url.username or ''),
        'PASSWORD': unquote(url.password or ''),
        'HOST': url.hostname, 'PORT': str(url.port or 5432),
        'CONN_MAX_AGE': 0, 'DISABLE_SERVER_SIDE_CURSORS': True,
        'OPTIONS': {'sslmode': options.get('sslmode', ['require'])[0], 'connect_timeout': 10},
    }}
    if ON_VERCEL and DATABASES['default']['OPTIONS']['sslmode'] not in ('require', 'verify-ca', 'verify-full'):
        raise ImproperlyConfigured('DATABASE_URL debe exigir TLS en Vercel.')
elif os.getenv('DATABASE_ENGINE') == 'postgresql':
    DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', **{name: os.getenv(env, default) for name, env, default in [('NAME','PGDATABASE','ushlm'),('USER','PGUSER','ushlm'),('PASSWORD','PGPASSWORD',''),('HOST','PGHOST','localhost'),('PORT','PGPORT','5432')]}}}
else:
    if ON_VERCEL:
        raise ImproperlyConfigured('Configurá DATABASE_URL de Neon; SQLite no es persistente en Vercel.')
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}
AUTH_PASSWORD_VALIDATORS = [{'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'}, {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'}, {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'}, {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE = 'es-ar'
TIME_ZONE = 'America/Argentina/Ushuaia'
USE_TZ = True
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
LOGIN_URL = '/cuenta/login/'
