from django.shortcuts import render
from django.http import HttpResponse
from .models import Inventory, InventoryLogEntry
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db import transaction 
import json 
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
import csv
from datetime import datetime, timedelta
from django.db.models import Sum
from django.utils import timezone
from django.db.models import Q
import math
from .Numb import generate_usage
from django.db.models.functions import Lower

# Create your views here.

def index(request):
    return HttpResponse("Welcome to LIMS!" \
    "Laboratory Inventory Management System")

from django.shortcuts import render, redirect
# from .forms import LabSessionForm


def home(request):
    return render(request, 'inventory/home.html')

def inventory_list(request):
    # compute recent-usage-based reorder thresholds without N+1 queries
    lookback_days = 90
    lead_time_days = 14
    safety_days = 7
    since = timezone.now() - timedelta(days=lookback_days)

    # Annotate each Inventory with total used in the lookback window (single query)
    items = Inventory.objects.annotate(
        total_used_lookback=Sum(
            'inventorylogentry__amount_used',
            filter=Q(inventorylogentry__date_logged__gte=since, inventorylogentry__amount_used__lt=0)
        )
    ).order_by(Lower('item_name'))

    # Compute per-item derived reorder in Python (no additional DB calls)
    for it in items:
        # annotated sum is negative (consumption) because we filtered amount_used__lt=0; take abs
        total_used = abs(int(getattr(it, 'total_used_lookback') or 0))
        if total_used > 0:
            avg_daily = float(total_used) / float(lookback_days)
            computed = math.ceil(avg_daily * (lead_time_days + safety_days))
            it.computed_reorder = max(1, computed)
        else:
            # fallback to vendor_qty heuristic (mirror models logic)
            vq = getattr(it, 'vendor_qty', None) or 0
            try:
                vq_i = int(vq)
            except Exception:
                vq_i = 0
            if vq_i > 0:
                if vq_i <= 5:
                    it.computed_reorder = 1
                elif vq_i <= 20:
                    it.computed_reorder = max(1, vq_i // 5)
                else:
                    it.computed_reorder = max(1, vq_i // 10)
            else:
                it.computed_reorder = 1

        # Compute low-stock flag in-memory to avoid N+1 property calls in templates
        try:
            pred = it.predicted_needed
            if pred is not None:
                it.computed_low_stock = int(it.amount_in_stock or 0) < int(pred)
            else:
                it.computed_low_stock = int(it.amount_in_stock or 0) <= int(getattr(it, 'computed_reorder', 1) or 1)
        except Exception:
            it.computed_low_stock = False

    return render(request, 'inventory/inventory_list.html', {'items': items})

def inventory_search(request):
    search_text = request.GET.get('q', '')  # Get the search term from user input

    if search_text:
        results = Inventory.objects.filter(item_name__icontains=search_text)
        if not results.exists():  # If no items match the search
            results = None
    else:
        results = None  # No search term entered

    return render(request, 'inventory/inventory_search.html', {'results': results, 'query': search_text})


@require_POST
def update_quantity(request):
    # require authenticated user for changes so log entries always have a user
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return JsonResponse({"ok": False, "error": "authentication required"}, status=403)

    # require staff for write actions (JSON-friendly 403)
    if not request.user.is_staff:
        return JsonResponse({"ok": False, "error": "staff required"}, status=403)

    # expects JSON body: {"item_id": 123, "delta": -5, "notes": "Used in lab"}
    try:
        data = json.loads(request.body)
        item_id = int(data.get("item_id"))
        delta = int(data.get("delta"))   # negative to subtract, positive to add
        notes = data.get("notes", "")
    except Exception:
        return JsonResponse({"ok": False, "error": "invalid payload"}, status=400)

    # sanity checks: reject obviously insane deltas
    MAX_DELTA = 10_000_000
    if abs(delta) > MAX_DELTA:
        return JsonResponse({"ok": False, "error": "delta too large"}, status=400)

    try:
        with transaction.atomic():
            item = Inventory.objects.select_for_update().get(id=item_id)
            current = int(item.amount_in_stock or 0)

            # compute new amount with clamp to zero to avoid negative stock
            requested_new = current + delta
            new_amount = requested_new if requested_new >= 0 else 0

            # compute the applied delta (what will actually be logged)
            applied_delta = int(new_amount - current)

            # If nothing changes, return a no-op result
            if applied_delta == 0:
                return JsonResponse({"ok": False, "error": "no change applied", "current_amount": current}, status=400)

            # Create a signed log entry with the actual applied delta
            log_user = request.user
            InventoryLogEntry.objects.create(item=item, amount_used=applied_delta, notes=notes, user=log_user)

            # Persist the new amount
            item.amount_in_stock = new_amount
            item.save(update_fields=["amount_in_stock"])

        return JsonResponse({"ok": True, "previous_amount": current, "applied_delta": applied_delta, "new_amount": new_amount})
    except Inventory.DoesNotExist:
        return JsonResponse({"ok": False, "error": "item not found"}, status=404)


@require_POST
def update_plan(request):
    """API to update planning fields for an Inventory item.
    Expects JSON: {item_id, planned_reactions, students_per_reaction, units_per_reaction}
    Returns JSON {ok: True, predicted, units, low}
    """
    try:
        data = json.loads(request.body)
        item_id = int(data.get('item_id'))
    except Exception:
        return JsonResponse({'ok': False, 'error': 'invalid payload'}, status=400)

    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'error': 'authentication required'}, status=403)

    # require staff for plan updates (JSON-friendly 403)
    if not request.user.is_staff:
        return JsonResponse({'ok': False, 'error': 'staff required'}, status=403)

    try:
        with transaction.atomic():
            item = Inventory.objects.select_for_update().get(id=item_id)
            # parse and set fields, allow empty to clear
            def parse_int(v):
                if v is None or v == '':
                    return None
                return int(v)
            def parse_float(v):
                if v is None or v == '':
                    return None
                return float(v)

            item.planned_reactions = parse_int(data.get('planned_reactions'))
            item.students_per_reaction = parse_int(data.get('students_per_reaction'))
            item.units_per_reaction = parse_float(data.get('units_per_reaction'))
            item.save(update_fields=['planned_reactions', 'students_per_reaction', 'units_per_reaction'])

            predicted = item.predicted_needed
            return JsonResponse({'ok': True, 'predicted': predicted, 'units': item.units or '', 'low': item.is_low_stock})
    except Inventory.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'item not found'}, status=404)


def solutions_list(request): 
    return render(request, 'inventory/solutions_list.html')

def new_order(request):
    return render(request, 'inventory/new_order.html')

def usage_history(request):
    return render(request, 'inventory/usage_history.html')

def admin_dashboard(request):
    return render(request, 'inventory/admin_dashboard.html')

@staff_member_required
@login_required
def export_usage(request):
    """Web endpoint to export InventoryLogEntry data as CSV.
    - GET without params shows a small form.
    - GET with ?start=YYYY-MM-DD&end=YYYY-MM-DD&action=aggregate|rows returns CSV download.
    """
    start_str = request.GET.get('start')
    end_str = request.GET.get('end')
    action = request.GET.get('action', 'aggregate')

    if not start_str or not end_str:
        return render(request, 'inventory/export_usage.html')

    try:
        naive_start = datetime.strptime(start_str, '%Y-%m-%d')
        naive_end = datetime.strptime(end_str, '%Y-%m-%d') + timedelta(hours=23, minutes=59, seconds=59)
        # Make datetimes timezone-aware using current timezone to match DB values
        start = timezone.make_aware(naive_start, timezone.get_current_timezone())
        end = timezone.make_aware(naive_end, timezone.get_current_timezone())
    except Exception:
        return JsonResponse({'ok': False, 'error': 'invalid date format, use YYYY-MM-DD'}, status=400)

    rows_qs = InventoryLogEntry.objects.filter(date_logged__gte=start, date_logged__lte=end).select_related('item', 'user')

    if action == 'rows':
        filename = f'usage_rows_{start_str}_to_{end_str}.csv'
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        writer = csv.writer(response)
        # omit the standalone 'id' column (use item_id instead)
        writer.writerow(['item_id', 'item_name', 'sku', 'amount_used', 'notes', 'user', 'date_logged'])
        for r in rows_qs.order_by('date_logged'):
            writer.writerow([
                r.item.id if r.item_id else '',
                getattr(r.item, 'item_name', ''),
                getattr(r.item, 'sku', ''),
                r.amount_used,
                r.notes or '',
                str(r.user) if getattr(r, 'user', None) else '',
                r.date_logged.isoformat(),
            ])
        return response

    # default: aggregate
    # For 'aggregate' we now include every raw log row (so amount_used is visible for auditing)
    filename = f'usage_aggregate_rows_{start_str}_to_{end_str}.csv'
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    # omit the standalone 'id' column here as well
    writer.writerow(['item_id', 'item_name', 'sku', 'amount_used', 'notes', 'user', 'date_logged'])
    for r in rows_qs.order_by('item__sku', 'date_logged'):
        writer.writerow([
            r.item.id if r.item_id else '',
            getattr(r.item, 'item_name', ''),
            getattr(r.item, 'sku', ''),
            r.amount_used,
            r.notes or '',
            str(r.user) if getattr(r, 'user', None) else '',
            r.date_logged.isoformat(),
        ])
    return response

@staff_member_required
def run_numb(request):
    """Run the Numb generator from the web.

    Query params:
      start=YYYY-MM-DD
      end=YYYY-MM-DD
      action=summary|aggregate|rows  (default: summary)

    - summary: returns plain text usage summary
    - aggregate: returns aggregated CSV download
    - rows: returns raw rows CSV download (if any rows exist)
    """
    start_str = request.GET.get('start')
    end_str = request.GET.get('end')
    action = request.GET.get('action', 'summary')

    if not start_str or not end_str:
        return JsonResponse({'ok': False, 'error': 'provide start and end as YYYY-MM-DD query params'}, status=400)

    try:
        naive_start = datetime.strptime(start_str, '%Y-%m-%d')
        naive_end = datetime.strptime(end_str, '%Y-%m-%d') + timedelta(hours=23, minutes=59, seconds=59)
        # Make datetimes timezone-aware using current timezone to match DB values
        start = timezone.make_aware(naive_start, timezone.get_current_timezone())
        end = timezone.make_aware(naive_end, timezone.get_current_timezone())
    except Exception:
        return JsonResponse({'ok': False, 'error': 'invalid date format, use YYYY-MM-DD'}, status=400)

    # Use generate_usage for summary and rows; for aggregate, return the raw rows CSV (amount_used visible)
    if action == 'summary':
        _, _, summary = generate_usage(start, end, include_rows=True)
        return HttpResponse(summary, content_type='text/plain')

    if action == 'aggregate':
        # reuse generate_usage to obtain rows_csv, but return rows as the aggregate rows CSV
        aggregate_csv, rows_csv, summary = generate_usage(start, end, include_rows=True)
        if not rows_csv:
            return JsonResponse({'ok': False, 'error': 'no rows found in range'}, status=404)
        filename = f'numb_aggregate_{start_str}_to_{end_str}.csv'
        response = HttpResponse(rows_csv, content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    if action == 'rows':
        aggregate_csv, rows_csv, summary = generate_usage(start, end, include_rows=True)
        if not rows_csv:
            return JsonResponse({'ok': False, 'error': 'no rows found in range'}, status=404)
        filename = f'numb_rows_{start_str}_to_{end_str}.csv'
        response = HttpResponse(rows_csv, content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    return JsonResponse({'ok': False, 'error': 'unknown action'}, status=400)