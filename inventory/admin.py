from django.contrib import admin, messages
from django.urls import reverse
from django.db import transaction
from datetime import date, timedelta
from .models import Inventory, InventoryLogEntry

# Register your models here.

class SnapshotReorderMixin:
    def snapshot_reorder(self, request, queryset):
        updated = 0
        for item in queryset:
            try:
                val = item.effective_reorder_level
                item.reorder_override = val
                item.save(update_fields=['reorder_override'])
                updated += 1
            except Exception:
                continue
        self.message_user(request, f'Snapped reorder_override for {updated} items', level=messages.SUCCESS)
    snapshot_reorder.short_description = 'Snapshot computed reorder to reorder_override'

    def undo_last_log(self, request, queryset):
        """Admin action: for each selected Inventory, delete its most recent log entry and reverse the stock change.
        InventoryLogEntry.amount_used stores a signed delta: positive = restock (stock added), negative = consumption (stock removed).
        To undo a log we subtract the stored signed delta from current stock (i.e. new_stock = current_stock - signed_delta).
        This reverses both restocks and consumptions correctly.
        """
        if not request.user.is_staff:
            self.message_user(request, 'Staff privileges required to perform undo.', level=messages.ERROR)
            return

        undone = 0
        skipped = 0
        from .models import InventoryLogEntry
        for item in queryset:
            try:
                with transaction.atomic():
                    # lock the row to avoid concurrent updates
                    locked_item = Inventory.objects.select_for_update().get(pk=item.pk)
                    last = InventoryLogEntry.objects.filter(item=locked_item).order_by('-date_logged').first()
                    if not last:
                        skipped += 1
                        continue
                    # reverse: subtract the signed delta to undo its effect
                    try:
                        delta = int(getattr(last, 'amount_used', 0) or 0)
                    except Exception:
                        delta = int(getattr(last, 'signed_delta', 0) or 0)

                    new_amount = int(locked_item.amount_in_stock or 0) - delta
                    if new_amount < 0:
                        new_amount = 0
                    locked_item.amount_in_stock = new_amount
                    locked_item.save(update_fields=['amount_in_stock'])
                    last.delete()
                    undone += 1
            except Exception:
                skipped += 1
                continue

        if undone:
            self.message_user(request, f'Undid {undone} log(s); {skipped} items had no logs or failed.', level=messages.SUCCESS)
        else:
            self.message_user(request, 'No logs undone (none found or permission issue).', level=messages.WARNING)
    undo_last_log.short_description = 'Undo last log for selected inventory items'

@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin, SnapshotReorderMixin):
    list_display = (
        'item_name', 'sku', 'vendor', 'location', 'amount_in_stock', 'units', 'predicted_needed', 'effective_reorder_level', 'reorder_override'
    )
    list_editable = (
        'sku', 'vendor', 'location', 'amount_in_stock', 'units', 'reorder_override'
    )
    list_filter = ('vendor', 'location')
    search_fields = ('item_name', 'sku', 'notes')
    actions = ['snapshot_reorder']
    # expose the undo action to admins
    actions += ['undo_last_log']

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(request, extra_context=extra_context)

    def save_model(self, request, obj, form, change):
        """Save the object and notify admin if units were auto-filled by model.save()."""
        super().save_model(request, obj, form, change)
        # transient flag set in model.save() when units was auto-filled
        if getattr(obj, '_auto_set_units', False):
            self.message_user(request, 'Units were auto-filled as "each" because units_per_reaction was provided but units was blank.', level=messages.WARNING)
            # clear the transient flag to avoid repeated notices
            try:
                delattr(obj, '_auto_set_units')
            except Exception:
                pass


@admin.register(InventoryLogEntry)
class InventoryLogEntryAdmin(admin.ModelAdmin):
    change_list_template = 'admin/inventory/inventorylogentry/change_list.html'
    list_display = ('item', 'amount_used', 'notes', 'date_logged')
    search_fields = ('item__item_name', 'notes')
    list_filter = ('date_logged',)

    actions = ['undo_selected_logs']

    def undo_selected_logs(self, request, queryset):
        """Admin action to undo (reverse) the selected InventoryLogEntry rows.
        For each selected log we update the related Inventory.amount_in_stock and delete the log.
        This action understands signed deltas: it subtracts the log.amount_used (signed) from stock to reverse it.
        """
        if not request.user.is_staff:
            self.message_user(request, 'Staff privileges required to perform undo.', level=messages.ERROR)
            return

        undone = 0
        failed = 0
        for log in queryset.select_related('item'):
            try:
                with transaction.atomic():
                    item = Inventory.objects.select_for_update().get(pk=log.item.pk)
                    try:
                        delta = int(getattr(log, 'amount_used', 0) or 0)
                    except Exception:
                        delta = int(getattr(log, 'signed_delta', 0) or 0)
                    new_amount = int(item.amount_in_stock or 0) - delta
                    if new_amount < 0:
                        new_amount = 0
                    item.amount_in_stock = new_amount
                    item.save(update_fields=['amount_in_stock'])
                    log.delete()
                    undone += 1
            except Exception:
                failed += 1
                continue

        if undone:
            self.message_user(request, f'Undid {undone} log(s); {failed} failures.', level=messages.SUCCESS)
        else:
            self.message_user(request, 'No logs undone.', level=messages.WARNING)
    undo_selected_logs.short_description = 'Undo selected log entries (restore stock and delete logs)'

    def changelist_view(self, request, extra_context=None):
        """Inject the run-numb URL into the changelist context so the template can render a button.
        Place the controls above the changelist to avoid overlapping the Add button in admin UI.
        """
        if extra_context is None:
            extra_context = {}
        extra_context['run_numb_url'] = reverse('run_numb')
        today = date.today()
        extra_context['run_numb_default_end'] = today.isoformat()
        extra_context['run_numb_default_start'] = (today - timedelta(days=30)).isoformat()
        return super().changelist_view(request, extra_context=extra_context)