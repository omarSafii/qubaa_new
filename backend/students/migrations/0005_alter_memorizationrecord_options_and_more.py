import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0004_memorizationrecord_evaluation'),
    ]

    operations = [
        migrations.AlterField(
            model_name='memorizationrecord',
            name='date',
            field=models.DateField(default=django.utils.timezone.localdate, verbose_name='تاريخ التسجيل'),
        ),
    ]
