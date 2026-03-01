import csv
from django.utils import timezone
from inventory.models import Inventory
from datetime import datetime

def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y'):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    print(f"Warning: Unable to parse date '{date_str}'. Setting to None.")
    return None

with open('inventory.csv', newline='', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)

    if '' in reader.fieldnames:
        reader.fieldnames = reader.fieldnames[1:]

    for row in reader:
        if '' in row:
            row.pop('')

        row = {k.strip(): v for k, v in row.items()}

        sku = row.get('SKU')
        if not sku:
            print(f"Skipping item '{row.get('Item Name')}' because SKU is empty")
            continue

        # Update existing record or create new one
        obj, created = Inventory.objects.update_or_create(
            SKU=sku,
            defaults={
                'reorder': row.get('Reorder') or None,
                'item_name': row['Item Name'],
                'vendor': row['Vendor'],
                'location': row['Location'],
                'sub_location': row.get('Sub-Location') or None,
                'location_detail': row.get('Location Details') or None,
                'amount_in_stock': int(row['Amount in Stock']) if row['Amount in Stock'] else 0,
                'units': row['Units'],
                'vendor_qty': int(row['Vendor Qty']) if row['Vendor Qty'] else None,
                'date_opened': parse_date(row.get('Date Opened')) or timezone.now().date(),
                'expiration_date': parse_date(row.get('Expiration Date')),
                'storage_temperature': row.get('Storage Temperature') or None,
                'storage_instructions': row.get('Storage Instructions') or None,
                'notes': row.get('Notes') or None,
                'URL': row.get('URL') or None,
            }
        )

        if created:
            print(f"Created: {sku} - {row.get('Item Name')}")
        else:
            print(f"Updated: {sku} - {row.get('Item Name')}")

print("CSV import complete!")
