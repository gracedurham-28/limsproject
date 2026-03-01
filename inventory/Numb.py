"""
Numb.py
Utility script to export InventoryLogEntry data to CSV and produce usage summaries between two dates.

Usage (zsh):
  python Numb.py --start 2025-01-01 --end 2025-10-30 --out usage_summary.csv --rows rows.csv

What it does:
- Exports individual log entries within the date range to `--rows` (CSV)
- Aggregates total `amount_used` per inventory item in the date range and writes to `--out` (CSV)
- Prints a short summary (total usage, top items, average daily usage per item)

This script runs as a standalone Django script; it sets DJANGO_SETTINGS_MODULE to `appsett.settings`.
No external AI is required — a simple, explainable summary is produced locally.

If you want to call an external AI for a natural-language summary, you can post-process the generated CSV with any AI service.
"""

import os
import sys
import csv
import argparse
from datetime import datetime, timedelta
import io
import html
from urllib.parse import quote
from django.db.models import Sum, Count, Q

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'appsett.settings')
import django
django.setup()

from inventory.models import InventoryLogEntry, Inventory


def parse_args():
    p = argparse.ArgumentParser(description='Export InventoryLogEntry usage and summarize between two dates')
    p.add_argument('--start', required=True, help='Start date (inclusive) YYYY-MM-DD')
    p.add_argument('--end', required=True, help='End date (inclusive) YYYY-MM-DD')
    p.add_argument('--out', default='usage_aggregate.csv', help='Output CSV for aggregated usage per item')
    p.add_argument('--rows', default=None, help='Optional CSV file to export raw log rows')
    p.add_argument('--top', type=int, default=10, help='How many top items to print')
    return p.parse_args()


def to_date(s):
    return datetime.strptime(s, '%Y-%m-%d')


def export_rows(rows_qs, rows_path):
    fieldnames = ['item_id', 'item_name', 'sku', 'amount_used', 'units', 'notes', 'user', 'date_logged']
    with open(rows_path, 'w', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows_qs.order_by('date_logged'):
            writer.writerow({
                'item_id': r.item.id if r.item_id else '',
                'item_name': getattr(r.item, 'item_name', ''),
                'sku': getattr(r.item, 'sku', ''),
                'amount_used': r.amount_used,
                'units': getattr(r.item, 'units', '') or '',
                'notes': r.notes or '',
                'user': str(r.user) if getattr(r, 'user', None) else '',
                'date_logged': r.date_logged.isoformat(),
            })
    print(f'Wrote {rows_path}')


def export_aggregate(rows_qs, agg_path, start_date, end_date):
    # Aggregate consumption and restock per item
    agg = rows_qs.values('item').annotate(
        consumption=Sum('amount_used', filter=Q(amount_used__lt=0)),
        restock=Sum('amount_used', filter=Q(amount_used__gt=0)),
        count=Count('id')
    ).order_by('-consumption')
    with open(agg_path, 'w', newline='') as fh:
        fieldnames = ['item_id', 'item_name', 'sku', 'total_used', 'entries_count', 'units']
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        days = max(1, (end_date - start_date).days + 1)
        for row in agg:
            try:
                item = Inventory.objects.get(pk=row['item'])
                name = item.item_name
                sku = item.sku or ''
                units = item.units or ''
            except Inventory.DoesNotExist:
                name = ''
                sku = ''
                units = ''
            consumption = abs(row.get('consumption') or 0)
            restock = row.get('restock') or 0
            writer.writerow({
                'item_id': row['item'],
                'item_name': name,
                'sku': sku,
                'total_used': consumption,
                'entries_count': row['count'],
                'units': units,
            })
    print(f'Wrote aggregate to {agg_path}')


def print_summary(rows_qs, start_date, end_date, top=10):
    days = max(1, (end_date - start_date).days + 1)
    # total usage should reflect consumption only
    total_neg = rows_qs.filter(amount_used__lt=0).aggregate(total=Sum('amount_used'))['total'] or 0
    total_used = abs(total_neg)
    print('\nUSAGE SUMMARY')
    print('Date range:', start_date.date(), 'to', end_date.date(), f'({days} days)')
    print('Total amount used (all items):', total_used)

    # top items
    agg = rows_qs.filter(amount_used__lt=0).values('item').annotate(consumption=Sum('amount_used', filter=Q(amount_used__lt=0))).order_by('-consumption')[:top]
    if not agg:
        print('No log entries in the range.')
        return

    print('\nTop items:')
    for row in agg:
        try:
            item = Inventory.objects.get(pk=row['item'])
            name = item.item_name
            sku = item.sku or ''
            units = item.units or ''
        except Inventory.DoesNotExist:
            name = ''
            sku = ''
            units = ''
        print('-', name, f'(sku={sku})', 'total_used=', abs(row['consumption']), f'units={units}')

    # simple heuristics
    print('\n(Displayed totals are in each item\'s units)')


def generate_usage(start_date, end_date, include_rows=False, top=10):
    """Generate CSV strings and a textual summary for the given date range.

    Returns a tuple: (aggregate_csv_str, rows_csv_str_or_None, summary_text)
    """
    # make sure start/end are datetimes
    if not hasattr(start_date, 'date'):
        raise ValueError('start_date must be a datetime')
    if not hasattr(end_date, 'date'):
        raise ValueError('end_date must be a datetime')

    rows_qs = InventoryLogEntry.objects.filter(date_logged__gte=start_date, date_logged__lte=end_date)

    # build rows CSV in-memory if requested
    rows_csv = None
    if include_rows:
        buf = io.StringIO()
        writer = csv.writer(buf)
        # omit the standalone 'id' column (use item_id instead)
        writer.writerow(['item_id', 'item_name', 'sku', 'amount_used', 'units', 'notes', 'user', 'date_logged'])
        for r in rows_qs.order_by('date_logged'):
            writer.writerow([
                r.item.id if r.item_id else '',
                getattr(r.item, 'item_name', ''),
                getattr(r.item, 'sku', ''),
                r.amount_used,
                getattr(r.item, 'units', '') or '',
                r.notes or '',
                str(r.user) if getattr(r, 'user', None) else '',
                r.date_logged.isoformat(),
            ])
        rows_csv = buf.getvalue()
        buf.close()

    # aggregate consumption/restock per item
    buf = io.StringIO()
    writer = csv.writer(buf)
    agg = rows_qs.values('item').annotate(
        consumption=Sum('amount_used', filter=Q(amount_used__lt=0)),
        restock=Sum('amount_used', filter=Q(amount_used__gt=0)),
    )
    writer.writerow(['item_id', 'item_name', 'sku', 'total_used', 'entries_count', 'units'])
    for row in agg.order_by('-consumption'):
        try:
            item = Inventory.objects.get(pk=row['item'])
            name = item.item_name
            sku = item.sku or ''
            units = item.units or ''
        except Inventory.DoesNotExist:
            name = ''
            sku = ''
            units = ''
        total = abs(row.get('consumption') or 0)
        # entries_count isn't available in this aggregation call; compute via a small count
        count = InventoryLogEntry.objects.filter(item_id=row['item'], date_logged__gte=start_date, date_logged__lte=end_date).count()
        writer.writerow([row['item'], name, sku, total, count, units])
    aggregate_csv = buf.getvalue()
    buf.close()

    # textual summary
    total_used = abs(rows_qs.filter(amount_used__lt=0).aggregate(total=Sum('amount_used'))['total'] or 0)
    parts = []
    parts.append('USAGE SUMMARY')
    parts.append(f'Date range: {start_date.date()} to {end_date.date()}')
    parts.append(f'Total amount used (all items): {total_used}')

    agg_top = rows_qs.filter(amount_used__lt=0).values('item').annotate(consumption=Sum('amount_used', filter=Q(amount_used__lt=0))).order_by('-consumption')[:top]
    if not agg_top:
        parts.append('\nNo log entries in the range.')
    else:
        parts.append('\nTop items:')
        for row in agg_top:
            try:
                item = Inventory.objects.get(pk=row['item'])
                name = item.item_name
                sku = item.sku or ''
                units = item.units or ''
            except Inventory.DoesNotExist:
                name = ''
                sku = ''
                units = ''
            parts.append(f"- {name} (sku={sku}) total_used={abs(row['consumption'])} units={units}")

    parts.append('\n(Displayed totals are in each item\'s units)')

    summary = '\n'.join(parts)

    return aggregate_csv, rows_csv, summary


def main():
    args = parse_args()
    try:
        start = to_date(args.start)
        end = to_date(args.end) + timedelta(hours=23, minutes=59, seconds=59)
    except Exception as e:
        print('Invalid dates:', e)
        sys.exit(1)

    rows_qs = InventoryLogEntry.objects.filter(date_logged__gte=start, date_logged__lte=end)

    if args.rows:
        export_rows(rows_qs, args.rows)

    export_aggregate(rows_qs, args.out, start, end)
    print_summary(rows_qs, start, end, top=args.top)


if __name__ == '__main__':
    main()
