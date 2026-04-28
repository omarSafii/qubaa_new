import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('halaqas', '0002_halaqa_is_active_halaqa_shareable_link'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pointtransaction',
            name='date',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
