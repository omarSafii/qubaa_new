from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("halaqas", "0006_category_teacherassignment_alter_halaqa_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="attendance",
            name="recorded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="recorded_attendances",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="attendance",
            name="recorded_by_role",
            field=models.CharField(
                blank=True,
                choices=[
                    ("teacher", "أستاذ"),
                    ("supervisor", "موجه"),
                    ("admin", "أدمن"),
                ],
                default="",
                max_length=20,
            ),
        ),
    ]
