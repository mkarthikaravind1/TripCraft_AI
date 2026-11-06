from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from planner.models import UserProfile

# Demo registrations. Emails use example.com, a domain reserved for examples,
# and the accounts get unusable passwords, so nobody can log in as them.
SAMPLE_USERS = [
    {"username": "sample_priya", "full_name": "Priya Sharma", "email": "priya.sharma@example.com",
     "home_city": "Chennai", "preferred_currency": "INR", "travel_pace": "balanced"},
    {"username": "sample_arjun", "full_name": "Arjun Mehta", "email": "arjun.mehta@example.com",
     "home_city": "Mumbai", "preferred_currency": "INR", "travel_pace": "packed"},
    {"username": "sample_ananya", "full_name": "Ananya Iyer", "email": "ananya.iyer@example.com",
     "home_city": "Bengaluru", "preferred_currency": "INR", "travel_pace": "relaxed"},
    {"username": "sample_rahul", "full_name": "Rahul Verma", "email": "rahul.verma@example.com",
     "home_city": "Dubai", "preferred_currency": "AED", "travel_pace": "balanced"},
    {"username": "sample_karthik", "full_name": "Karthik Aravind M", "email": "karthik.aravind@example.com",
     "home_city": "Kochi", "preferred_currency": "INR", "travel_pace": "relaxed"},
]


class Command(BaseCommand):
    help = (
        "Create or update 5 sample registered users (login disabled) and remove sample users that are no "
        "longer in the list. Safe to run repeatedly; real accounts are never touched."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        wanted = [data["username"] for data in SAMPLE_USERS]
        retired = User.objects.filter(profile__is_sample=True).exclude(username__in=wanted)
        removed = list(retired.values_list("username", flat=True))
        retired.delete()

        created_count = 0
        for data in SAMPLE_USERS:
            first, _, last = data["full_name"].partition(" ")
            user, created = User.objects.get_or_create(username=data["username"])
            user.email = data["email"]
            user.first_name, user.last_name = first, last
            user.is_staff = user.is_superuser = False
            user.set_unusable_password()
            user.save()
            UserProfile.objects.update_or_create(
                user=user,
                defaults={
                    "full_name": data["full_name"],
                    "home_city": data["home_city"],
                    "preferred_currency": data["preferred_currency"],
                    "travel_pace": data["travel_pace"],
                    "is_sample": True,
                },
            )
            created_count += created
        self.stdout.write(self.style.SUCCESS(
            f"Sample users ready: {len(SAMPLE_USERS)} total, {created_count} newly created (login disabled)."
            + (f" Removed: {', '.join(removed)}." if removed else "")
        ))
