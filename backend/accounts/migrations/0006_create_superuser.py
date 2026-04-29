from django.db import migrations

def create_superuser(apps, schema_editor):
    User = apps.get_model('auth', 'User')  # 👈 هذا مهم

    if not User.objects.filter(username="hamza").exists():
        User.objects.create_superuser(
            username="hamza",
            email="hamza@gmail.com",
            password="Hamza@123"
        )

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_superuser),
    ]