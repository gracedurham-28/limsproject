# Manually create missing InventoryLogEntry table when migration history shows it as applied but the table is absent.
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0009_create_inventorylogentry'),
    ]

    operations = [
        migrations.CreateModel(
            name='InventoryLogEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount_used', models.IntegerField()),
                ('notes', models.TextField(blank=True, null=True)),
                ('date_logged', models.DateTimeField(auto_now_add=True)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='inventory.inventory')),
            ],
        ),
    ]
