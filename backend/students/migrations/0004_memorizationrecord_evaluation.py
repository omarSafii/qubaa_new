from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0003_alter_memorizationrecord_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='memorizationrecord',
            name='evaluation',
            field=models.CharField(
                blank=True,
                choices=[
                    ('excellent', 'ممتاز'),
                    ('very_good', 'جيد جدًا'),
                    ('good', 'جيد'),
                    ('needs_followup', 'يحتاج متابعة'),
                ],
                max_length=20,
                verbose_name='تقييم التسميع',
            ),
        ),
    ]
