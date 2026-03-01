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

from .settings import *  # import base settings

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

# Make tests verbose by default
TEST_RUNNER = 'django.test.runner.DiscoverRunner'
