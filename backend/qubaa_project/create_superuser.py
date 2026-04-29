from django.contrib.auth import get_user_model

def create_superuser():
    User = get_user_model()
    if not User.objects.filter(username="hamza").exists():
        User.objects.create_superuser(
            username="hamza",
            email="hamza@gmail.com",
            password="Hamza@123"
        )