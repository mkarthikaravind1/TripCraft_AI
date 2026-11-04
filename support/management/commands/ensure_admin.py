import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Create (or reset the password of) a Django admin from DJANGO_SUPERUSER_USERNAME and "
        "DJANGO_SUPERUSER_PASSWORD. Does nothing if they are not set. Used by build.sh on Render, "
        "where the free plan has no shell for `createsuperuser`."
    )

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        if not username or not password:
            self.stdout.write("Admin account not configured (DJANGO_SUPERUSER_* not set); skipping.")
            return
        if len(password) < 12:
            self.stderr.write("DJANGO_SUPERUSER_PASSWORD must be at least 12 characters; admin not changed.")
            return

        User = get_user_model()
        user, created = User.objects.get_or_create(username=username)
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Admin account '{username}' {'created' if created else 'updated'}."))
