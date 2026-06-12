from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("halaqas", "0008_homework_expected_recitation_details"),
    ]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="total_pages",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
