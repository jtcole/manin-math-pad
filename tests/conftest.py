"""Django integration test fixtures and settings."""
import os
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

if not settings.configured:
    settings.configure(
        DATABASES=DATABASES,
        INSTALLED_APPS=INSTALLED_APPS,
        ROOT_URLCONF=ROOT_URLCONF,
        DEFAULT_AUTO_FIELD=DEFAULT_AUTO_FIELD,
        SECRET_KEY='test-secret-key-manin-math-pad',
    )
    django.setup()