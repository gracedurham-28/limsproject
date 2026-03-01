from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib import admin
from django.utils import timezone
from datetime import timedelta
from inventory.models import Inventory, InventoryLogEntry
from inventory import admin as inv_admin

User = get_user_model()

class SignedDeltaUndoTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        # create a staff user
        self.staff = User.objects.create_user(username='staff', password='pw', email='staff@example.com')
        self.staff.is_staff = True
        self.staff.save()

    def _make_request(self):
        req = self.factory.post('/')
        req.user = self.staff
        # attach a session to the RequestFactory request so message storage works
        from django.contrib.sessions.middleware import SessionMiddleware
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(req)
        # ensure session can be saved during the test run
        req.session.save()
        from django.contrib.messages.storage.fallback import FallbackStorage
        req._messages = FallbackStorage(req)
        return req

    def test_undo_consumption_log_increases_stock_and_deletes_log(self):
        inv = Inventory.objects.create(item_name='Test Item', amount_in_stock=10, sku='TSTSKU1')
        # create a consumption log (negative)
        log = InventoryLogEntry.objects.create(item=inv, amount_used=-3, notes='used', user=self.staff)
        # call admin action
        admin_obj = inv_admin.InventoryLogEntryAdmin(InventoryLogEntry, admin.site)
        req = self._make_request()
        qs = InventoryLogEntry.objects.filter(pk=log.pk)
        admin_obj.undo_selected_logs(req, qs)
        inv.refresh_from_db()
        # stock should have increased by 3 (undo consumption)
        self.assertEqual(inv.amount_in_stock, 13)
        # log should be deleted
        self.assertFalse(InventoryLogEntry.objects.filter(pk=log.pk).exists())

    def test_undo_restock_log_decreases_stock_and_deletes_log(self):
        inv = Inventory.objects.create(item_name='Test Item 2', amount_in_stock=5, sku='TSTSKU2')
        # create a restock log (positive)
        log = InventoryLogEntry.objects.create(item=inv, amount_used=4, notes='restock', user=self.staff)
        admin_obj = inv_admin.InventoryLogEntryAdmin(InventoryLogEntry, admin.site)
        req = self._make_request()
        qs = InventoryLogEntry.objects.filter(pk=log.pk)
        admin_obj.undo_selected_logs(req, qs)
        inv.refresh_from_db()
        # stock should have decreased by 4 (undo restock)
        self.assertEqual(inv.amount_in_stock, 1)
        self.assertFalse(InventoryLogEntry.objects.filter(pk=log.pk).exists())

    def test_effective_reorder_level_uses_consumption_only(self):
        # create inventory with vendor_qty small
        inv = Inventory.objects.create(item_name='Test Item 3', amount_in_stock=50, sku='TSTSKU3', vendor_qty=10)
        # create logs: a large restock and a consumption in the last 90 days
        now = timezone.now()
        # restock of +1000 (should be ignored for consumption calculation)
        InventoryLogEntry.objects.create(item=inv, amount_used=1000, notes='big restock', user=self.staff, date_logged=now - timedelta(days=10))
        # consumption of -1800 over lookback window
        InventoryLogEntry.objects.create(item=inv, amount_used=-1800, notes='heavy use', user=self.staff, date_logged=now - timedelta(days=5))
        # effective_reorder_level should be computed from consumption only and be > vendor heuristic (which would be small)
        erl = inv.effective_reorder_level
        self.assertTrue(erl > 1)
        # sanity: with 1800 consumption over 90 days, expected computed > vendor heuristic
        self.assertTrue(erl > 10)
