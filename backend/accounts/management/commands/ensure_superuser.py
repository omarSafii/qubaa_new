import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import Profile


def env_flag(name):
    value = os.getenv(name, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Command(BaseCommand):
    help = "Create or update the configured Django superuser after migrations."

    def handle(self, *args, **options):
        username = os.getenv("DJANGO_SUPERUSER_USERNAME", "").strip()
        email = os.getenv("DJANGO_SUPERUSER_EMAIL", "").strip()
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD", "")
        reset_password = env_flag("DJANGO_SUPERUSER_RESET_PASSWORD")

        if not username or not password:
            self.stdout.write(
                self.style.WARNING(
                    "Skipping ensure_superuser: set DJANGO_SUPERUSER_USERNAME and "
                    "DJANGO_SUPERUSER_PASSWORD to create or update the admin user."
                )
            )
            return

        User = get_user_model()
        username_field = User.USERNAME_FIELD
        lookup = {username_field: username}

        user = User._default_manager.filter(**lookup).first()
        created = False
        changed_fields = []

        if user is None:
            create_kwargs = {
                username_field: username,
                "password": password,
            }
            if hasattr(User, "email"):
                create_kwargs["email"] = email

            user = User._default_manager.create_superuser(**create_kwargs)
            created = True
        else:
            if email and hasattr(user, "email") and user.email != email:
                user.email = email
                changed_fields.append("email")
            if not user.is_staff:
                user.is_staff = True
                changed_fields.append("is_staff")
            if not user.is_superuser:
                user.is_superuser = True
                changed_fields.append("is_superuser")
            if not user.is_active:
                user.is_active = True
                changed_fields.append("is_active")
            if reset_password:
                user.set_password(password)
                changed_fields.append("password")

            if changed_fields:
                user.save()

        profile, profile_created = Profile.objects.get_or_create(user=user)

        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created superuser '{username}'"
                    + (" and profile." if profile_created else ".")
                )
            )
            return

        if changed_fields or profile_created:
            details = []
            if changed_fields:
                details.append(f"updated {', '.join(changed_fields)}")
            if profile_created:
                details.append("created missing profile")
            self.stdout.write(
                self.style.SUCCESS(
                    f"Ensured superuser '{username}': " + "; ".join(details) + "."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Superuser '{username}' already exists and required no changes."
            )
        )
