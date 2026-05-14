"""Django integration test fixtures and settings."""
import django
from django.conf import settings

# Minimal Django settings for running tests without the full site
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'manin_math_pad',
]

ROOT_URLCONF = 'tests.test_urls'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {},
    },
]

if not settings.configured:
    settings.configure(
        DATABASES=DATABASES,
        INSTALLED_APPS=INSTALLED_APPS,
        ROOT_URLCONF=ROOT_URLCONF,
        DEFAULT_AUTO_FIELD=DEFAULT_AUTO_FIELD,
        TEMPLATES=TEMPLATES,
        MEDIA_ROOT='/tmp/manin_math_pad_test_media',
        SECRET_KEY='test-secret-key-manin-math-pad',
    )
    django.setup()
