from django.conf import settings
from django.db import migrations


def ensure_profiles(apps, schema_editor):
    user_app_label, user_model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(user_app_label, user_model_name)
    Profile = apps.get_model("accounts", "Profile")
    db_alias = schema_editor.connection.alias

    existing_profile_user_ids = set(
        Profile.objects.using(db_alias).values_list("user_id", flat=True)
    )
    missing_user_ids = User.objects.using(db_alias).exclude(
        id__in=existing_profile_user_ids
    ).values_list("id", flat=True)

    Profile.objects.using(db_alias).bulk_create(
        [Profile(user_id=user_id) for user_id in missing_user_ids],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0007_merge_0001_initial_0006_create_superuser"),
    ]

    operations = [
        migrations.RunPython(ensure_profiles, migrations.RunPython.noop),
    ]
