from django.db import models
from django.utils import timezone 
from datetime import timedelta
import random
import math
from django.db.models import Sum
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
import uuid
from django.db import IntegrityError

def generate_unique_sku():
    # stronger SKU generator using UUID4 hex (12 chars) to reduce collision risk
    # returns an uppercase alphanumeric SKU, length <= 15
    return uuid.uuid4().hex[:12].upper()

class InventoryLogEntry(models.Model):
    item = models.ForeignKey('Inventory', on_delete=models.CASCADE)
    amount_used = models.IntegerField()
    notes = models.TextField(blank=True, null=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    date_logged = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        """Store a signed delta in `amount_used`: positive = restock, negative = consumption.
        Preserve the sign but normalize to an int. We don't auto-apply to Inventory here; views
        and admin actions are responsible for applying the delta atomically.
        """
        try:
            if self.amount_used is not None:
                # preserve sign, but coerce to int
                self.amount_used = int(self.amount_used)
        except Exception:
            # If coercion fails, let model validation surface the problem
            pass
        return super().save(*args, **kwargs)

    @property
    def signed_delta(self):
        """Return the signed integer delta this log entry represents.
        Positive for restock, negative for consumption.
        """
        try:
            return int(self.amount_used or 0)
        except Exception:
            return 0

    def __str__(self):
        # Display the signed amount directly (e.g. '+3' or '-2') to avoid ambiguity
        try:
            amt = int(self.amount_used or 0)
        except Exception:
            amt = self.amount_used or 0
        sign = '+' if amt >= 0 else ''
        return f"{self.item.item_name}: {sign}{amt} @ {self.date_logged} ({self.user})"

class Inventory(models.Model): 
    item_name = models.CharField(max_length=200, verbose_name='Item Name')
    sku = models.CharField(
        max_length=15,
        verbose_name='SKU',
        unique=True,
        default=generate_unique_sku,
        blank=True, 
        null=True
    )
    # allow blank values so admin list_editable can clear these fields
    vendor = models.CharField(max_length=40, verbose_name='Vendor', blank=True, null=True)
    location = models.CharField(max_length=35, verbose_name='Location', blank=True, null=True)
    sub_location = models.CharField(max_length=35, verbose_name='Sub-location', blank=True, null=True)
    location_detail = models.CharField(max_length=50, verbose_name='Location Detail', blank=True, null=True)
    amount_in_stock = models.PositiveIntegerField(verbose_name='Amount in Stock')
    # Optional manual override for reorder threshold (persisted). Use when you want to lock a value.
    reorder_override = models.IntegerField(blank=True, null=True, help_text='Manual override for reorder threshold (persists until cleared)')
    # Planning fields for predictive per-reaction needs
    planned_reactions = models.PositiveIntegerField(verbose_name='Planned Reactions', blank=True, null=True,
                                                   help_text='Number of reactions planned for upcoming session (optional)')
    students_per_reaction = models.PositiveIntegerField(verbose_name='Students per Reaction', blank=True, null=True,
                                                        help_text='How many students run each reaction (used to compute total needed)')
    units_per_reaction = models.FloatField(verbose_name='Units per Reaction', blank=True, null=True,
                                         help_text='How many units of this item one reaction consumes (e.g. 1, 0.5)')
    units = models.CharField(max_length=80, verbose_name='Units', blank=True, null=True,
                             help_text='Human-readable unit name (e.g. "each", "mL", "g"). If units_per_reaction is set and units is blank, units will default to "each".')
    vendor_qty = models.PositiveIntegerField(verbose_name='Vendor Qty', blank=True, null=True)
    date_opened = models.DateField(verbose_name='Date Opened', blank=True, null=True)
    expiration_date = models.DateField(verbose_name='Expiration Date', blank=True, null=True)
    storage_temperature = models.CharField(max_length=20, verbose_name='Storage Temperature', blank=True, null=True)
    storage_instructions = models.TextField(verbose_name='Storage Instructions', blank=True, null=True)
    notes = models.TextField(verbose_name='Notes', blank=True, null=True)
    url = models.URLField(verbose_name='URL', blank=True, null=True)

    def __str__(self):
        return f"{self.item_name} ({self.sku})"

    def save(self, *args, **kwargs):
        """Ensure SKU uniqueness and set sensible defaults for units if needed.
        If units_per_reaction is provided but units is empty, default units to 'each'.
        """
        # If units_per_reaction provided but units blank, default to 'each' and mark for admin notice
        try:
            if (self.units_per_reaction is not None) and (not self.units or str(self.units).strip() == ''):
                self.units = 'each'
                # non-persistent flag used by admin to show a warning message
                try:
                    self._auto_set_units = True
                except Exception:
                    pass
        except Exception:
            pass

        # existing SKU generation / save logic
        # If sku already set, normal save
        if self.sku:
            return super().save(*args, **kwargs)

        # Try to generate and save with retries to avoid IntegrityError crashes
        max_attempts = 10
        last_exc = None
        for attempt in range(max_attempts):
            self.sku = generate_unique_sku()
            try:
                return super().save(*args, **kwargs)
            except IntegrityError as e:
                # possible unique constraint collision on sku; retry
                last_exc = e
                # clear primary key to ensure Django will INSERT on next attempt
                if getattr(self, 'pk', None) is not None:
                    self.pk = None
                continue
        # if we reach here, re-raise the last IntegrityError for visibility
        if last_exc:
            raise last_exc

    def clean(self):
        """Model-level validation: ensure units are present when units_per_reaction is provided.
        We auto-fill units in save(), but still validate that units_per_reaction is positive when set.
        """
        from django.core.exceptions import ValidationError
        if self.units_per_reaction is not None:
            try:
                if float(self.units_per_reaction) <= 0:
                    raise ValidationError({'units_per_reaction': 'units_per_reaction must be positive'})
            except (TypeError, ValueError):
                raise ValidationError({'units_per_reaction': 'units_per_reaction must be a number'})
        # no return; ValidationError will be raised by callers (admin/forms/mgmt commands)

    @property
    def effective_reorder_level(self):
        """Return a sensible per-item reorder threshold.
        Priority:
        1) persisted `reorder_override` if set (manual override)
        2) derive from recent usage (InventoryLogEntry)
        3) derive from `vendor_qty` when available
        4) fallback to 1
        This no longer relies on a persisted `reorder_level` column; values are computed on the fly.
        """
        # 0) manual override takes precedence
        try:
            if self.reorder_override is not None:
                v = int(self.reorder_override)
                if v >= 0:
                    return v
        except Exception:
            pass
        # usage-driven calculation
        lookback_days = 90
        lead_time_days = 14
        safety_days = 7
        since = timezone.now() - timedelta(days=lookback_days)
        try:
            # sum only consumption (negative stored values), take absolute total
            total_neg = InventoryLogEntry.objects.filter(item=self, date_logged__gte=since, amount_used__lt=0).aggregate(total=Sum('amount_used'))['total'] or 0
            total_used = abs(total_neg)
        except Exception:
            total_used = 0

        if total_used and total_used > 0:
            avg_daily = float(total_used) / float(lookback_days)
            computed = math.ceil(avg_daily * (lead_time_days + safety_days))
            return max(1, computed)

        # 3) vendor_qty heuristic
        vq = getattr(self, 'vendor_qty', None)
        try:
            if vq:
                v = int(vq)
                if v <= 5:
                    return 1
                if v <= 20:
                    return max(1, v // 5)
                return max(1, v // 10)
        except Exception:
            pass

        # fallback
        return 1

    @property
    def predicted_needed(self):
        """Compute the total units needed for the planned reactions.

        Priority:
        - If `planned_reactions` is set, compute: ceil(planned_reactions * (students_per_reaction or 1) * (units_per_reaction or 1)).
        - Otherwise return None so other reorder logic can apply.
        """
        try:
            pr = self.planned_reactions
            if not pr:
                return None
            students = self.students_per_reaction or 1
            upr = float(self.units_per_reaction) if (self.units_per_reaction is not None) else 1.0
            needed = math.ceil(float(pr) * float(students) * upr)
            # Treat zero as 'no meaningful value' so templates can show empty instead of 0
            if needed <= 0:
                return None
            return int(needed)
        except Exception:
            return None

    @property 
    def is_low_stock(self):
        """Check if the item is low in stock. Uses predicted_needed when available,
        otherwise falls back to effective_reorder_level."""
        try:
            pred = self.predicted_needed
            if pred is not None:
                return int(self.amount_in_stock or 0) < int(pred)
            # fallback to previously defined logic
            return int(self.amount_in_stock or 0) <= int(self.effective_reorder_level or 1)
        except Exception:
            return False

    class Meta:
        managed = True 
        db_table = 'inventory_inventory'
        ordering = ['item_name']
    

class Solutions(models.Model):
    item_name = models.CharField(max_length=200, verbose_name='Solution Name')
    SKU = models.CharField(max_length=15, verbose_name='SKU', unique=True)
    vendor = models.CharField(max_length=40, verbose_name='Vendor')
    location = models.CharField(max_length=35, verbose_name='Location')
    sub_location = models.CharField(max_length=35, verbose_name='Sub-location', blank=True, null=True)
    recipe_instructions = models.CharField(max_length=50, verbose_name='Recipe Instructions', blank=True, null=True)
    amount_in_stock = models.PositiveIntegerField(verbose_name='Amount in Stock')
    units = models.CharField(max_length=80, verbose_name='Units')
    URL = models.URLField(verbose_name='URL', blank=True, null=True)

    def __str__(self):
        return f"{self.item_name} ({self.SKU})"

class Usage_History(models.Model):
    date = models.DateField(verbose_name='Date', default=timezone.now)
    SKU = models.CharField(max_length=15, verbose_name='SKU')
    item_name = models.CharField(max_length=200, verbose_name='Item Name')
    vendor = models.CharField(max_length=40, verbose_name='Vendor')
    quantity_used = models.IntegerField(verbose_name='Quantity Used')
    stock_remaining = models.IntegerField(verbose_name='Stock Remaining')
    units = models.CharField(max_length=50, verbose_name='Units')

    def __str__(self):
        return f"Usage of {self.inventory_item.item_name} on {self.date_used}"
    
class New_Order(models.Model):
    item_name = models.CharField(max_length=200, verbose_name='Item Name')
    vendor = models.CharField(max_length=40, verbose_name='Vendor')
    amount_requested = models.PositiveIntegerField(verbose_name='Amount Requested')
    vendor_qty = models.PositiveIntegerField(verbose_name='Vendor Quantity', blank=True, null=True)
    units = models.CharField(max_length=80, verbose_name='Units')
    URL = models.URLField(verbose_name='URL', blank=True, null=True)

    def __str__(self):
        return f"Order Request: {self.item_name} from {self.vendor}"


def _compute_dynamic_reorder(item, lookback_days=90, lead_time_days=14, safety_days=7):
    """Compute reorder threshold from recent usage or vendor_qty.
    This function ignores the stored `reorder_level` so it can be used to
    automatically populate/update that column for all items.
    """
    # usage-driven calculation
    since = timezone.now() - timedelta(days=lookback_days)
    try:
        # sum only consumption (negative stored values), take absolute total
        total_neg = InventoryLogEntry.objects.filter(item=item, date_logged__gte=since, amount_used__lt=0).aggregate(total=Sum('amount_used'))['total'] or 0
        total_used = abs(total_neg)
    except Exception:
        total_used = 0

    if total_used and total_used > 0:
        avg_daily = float(total_used) / float(lookback_days)
        computed = math.ceil(avg_daily * (lead_time_days + safety_days))
        return max(1, computed)

    # vendor_qty heuristic fallback
    vq = getattr(item, 'vendor_qty', None)
    try:
        if vq:
            v = int(vq)
            if v <= 5:
                return 1
            if v <= 20:
                return max(1, v // 5)
            return max(1, v // 10)
    except Exception:
        pass

    # final fallback
    return 1

