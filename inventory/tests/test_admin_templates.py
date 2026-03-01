from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from inventory.models import Inventory

User = get_user_model()

class AdminTemplateTests(TestCase):
    def setUp(self):
        # create a staff user
        self.staff = User.objects.create_user(username='staff', password='password')
        self.staff.is_staff = True
        self.staff.is_superuser = True
        self.staff.save()
        # create a sample inventory item
        self.item = Inventory.objects.create(item_name='Test Item', amount_in_stock=10)
        self.client = Client()

    def test_inventory_changelist_renders_custom_controls(self):
        self.client.login(username='staff', password='password')
        url = reverse('admin:inventory_inventory_changelist')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        # check that the run-numb form is present in the response
        self.assertContains(resp, 'id="run-numb-form"')

    def test_inventorylogentry_changelist_renders_custom_controls(self):
        self.client.login(username='staff', password='password')
        url = reverse('admin:inventory_inventorylogentry_changelist')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="run-numb-form"')

    def test_api_write_endpoints_require_staff(self):
        # ensure non-authenticated and non-staff users get JSON 403 for write endpoints
        update_url = reverse('api_update_quantity')
        resp = self.client.post(update_url, data='{}', content_type='application/json')
        self.assertEqual(resp.status_code, 403)
        # login as a non-staff user
        user = User.objects.create_user(username='normal', password='pw')
        self.client.login(username='normal', password='pw')
        resp = self.client.post(update_url, data='{}', content_type='application/json')
        self.assertEqual(resp.status_code, 403)
