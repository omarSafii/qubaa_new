from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_ensure_profiles"),
    ]

    operations = [
        migrations.AlterField(
            model_name="profile",
            name="role",
            field=models.CharField(
                choices=[
                    ("parent", "ولي أمر"),
                    ("teacher", "أستاذ"),
                    ("supervisor", "موجه"),
                    ("admin", "أدمن"),
                ],
                default="parent",
                max_length=10,
            ),
        ),
    ]
