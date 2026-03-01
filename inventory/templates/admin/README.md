Overridden admin templates for the `inventory` app

Files and purpose
- `inventory/templates/admin/inventory/inventory/change_list.html`
  - Adds a small "Run Numb" form to the Inventory changelist to run the Numb exporter from the admin UI (summary/aggregate/rows). Expects the view/context to provide `run_numb_url`, `run_numb_default_start`, `run_numb_default_end`.
- `inventory/templates/admin/inventory/inventorylogentry/change_list.html`
  - Similar UI added to the InventoryLogEntry changelist for convenience.

Why these are overridden
- These templates inject custom controls and JS into Django's admin `change_list` rendering. They rely on the admin base `change_list.html` blocks and a couple of stable block names (`content` / `object-tools`). If Django changes the admin template API, these overrides may fail to render.

Dependencies
- The templates include a small inline script that submits the form to the URL provided in context (`run_numb_url`). No additional static assets are required.

Tests
- See `inventory/tests/test_admin_templates.py` — tests assert the presence of the `id="run-numb-form"` marker and verify the pages render for a staff user.

Upgrading Django
- When upgrading Django, run the admin-template tests and manually visit the admin changelist pages. If rendering fails, compare the overridden template against the upstream `django/contrib/admin/templates/admin/change_list.html` to find renamed/removed blocks.

How to run tests locally
- From the repository root (virtualenv activated):
  - python manage.py migrate --noinput
  - python manage.py test inventory.tests.test_admin_templates

Tips for maintainers
- Keep the inline JS small and defensive. Prefer feature-detection and basic form submission so upgrades are less likely to break.
- If a template block used here is removed upstream, prefer adapting the override to use the new block rather than copying large portions of the upstream template.
