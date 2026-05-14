"""Django integration test fixtures and settings."""
import django
import pytest
from django.conf import settings
from django.core.management import call_command

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
    'manim_math_pad',
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
        MEDIA_ROOT='/tmp/manim_math_pad_test_media',
        SECRET_KEY='test-secret-key-manim-math-pad',
    )
    django.setup()


@pytest.fixture
def migrated_db(db):
    """Create the in-memory SQLite schema for endpoint tests."""
    call_command('migrate', verbosity=0, interactive=False)

    from manim_math_pad.models import Animation, Message, Session, ZettelCluster

    Animation.objects.all().delete()
    Message.objects.all().delete()
    ZettelCluster.objects.all().delete()
    Session.objects.all().delete()
    yield
    Animation.objects.all().delete()
    Message.objects.all().delete()
    ZettelCluster.objects.all().delete()
    Session.objects.all().delete()
