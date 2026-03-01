"""
Lightweight test settings used only for running unit tests locally/CI when
migrations for the app under test are unstable. This file intentionally keeps
changes isolated to the test run and should NOT be used in production.

What it does:
- Uses an in-memory SQLite database to avoid touching Postgres or your development DB.
- Disables migrations for the `inventory` app so Django will create tables from
  the current models directly instead of running potentially-broken migrations.

Usage:
  python manage.py test inventory.tests.test_admin_templates --settings=appsett.test_settings

"""

import os
from appsett.settings import *  # import base settings (safe because we override below)

# Ensure session and message middleware exist and are ordered correctly for tests
MIDDLEWARE = list(globals().get('MIDDLEWARE', []))
# Guarantee session middleware present
if 'django.contrib.sessions.middleware.SessionMiddleware' not in MIDDLEWARE:
    MIDDLEWARE.insert(0, 'django.contrib.sessions.middleware.SessionMiddleware')
# Guarantee message middleware present and placed after session middleware
if 'django.contrib.messages.middleware.MessageMiddleware' not in MIDDLEWARE:
    try:
        idx = MIDDLEWARE.index('django.contrib.sessions.middleware.SessionMiddleware') + 1
    except ValueError:
        idx = 0
    MIDDLEWARE.insert(idx, 'django.contrib.messages.middleware.MessageMiddleware')

# Ensure session and messages apps are enabled for tests
INSTALLED_APPS = list(globals().get('INSTALLED_APPS', []))
for app in ('django.contrib.sessions', 'django.contrib.messages'):
    if app not in INSTALLED_APPS:
        INSTALLED_APPS.append(app)

# Ensure tests never pick up production secrets
SECRET_KEY = os.getenv('DJANGO_TEST_SECRET_KEY', 'test-secret-key')
# Enable debug for faster failure output in test runs
DEBUG = True
# Restrict allowed hosts for test environment
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']

# Use an in-memory sqlite DB for tests so the real DB is untouched
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Disable migrations for the inventory app during tests. This makes the test
# runner create tables from models instead of executing migrations, which is
# useful for running quick tests when migrations are broken but model code is
# correct. You can add other apps here if needed.
MIGRATION_MODULES = {
    'inventory': None,
}

# Speed up password hashing during tests
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Keep emails in memory during tests
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Keep tests quiet and deterministic
LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
}

# Make tests verbose by default
TEST_RUNNER = 'django.test.runner.DiscoverRunner'

# Use cookie-based message storage in tests to avoid requiring session middleware
MESSAGE_STORAGE = 'django.contrib.messages.storage.cookie.CookieStorage'
