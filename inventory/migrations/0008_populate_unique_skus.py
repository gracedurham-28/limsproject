# Generated data migration to populate missing/duplicate SKUs before enforcing uniqueness
from django.db import migrations


def generate_unique_sku():
    import random
    return str(random.randint(1000000, 9999999))


def forwards(apps, schema_editor):
    Inventory = apps.get_model('inventory', 'Inventory')
    existing = set(x for x in Inventory.objects.values_list('sku', flat=True) if x)
    for item in Inventory.objects.all():
        # If sku is empty or there exists another item with same sku, assign a new unique sku
        if (not item.sku) or Inventory.objects.filter(sku=item.sku).exclude(pk=item.pk).exists():
            sku = generate_unique_sku()
            while sku in existing:
                sku = generate_unique_sku()
            item.sku = sku
            item.save(update_fields=['sku'])
            existing.add(sku)


def backwards(apps, schema_editor):
    # No-op to avoid removing SKUs on reverse
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0007_rename_url_inventory_url_remove_inventory_sku_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
