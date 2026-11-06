from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from planner.management.commands.seed_sample_users import SAMPLE_USERS
from planner.models import UserProfile


def registration(**overrides):
    data = {
        "full_name": "Kavya Raman",
        "email": "Kavya.Raman@Example.com",
        "username": "kavya",
        "password1": "travel-Plans-2026",
        "password2": "travel-Plans-2026",
        "home_city": "Madurai",
        "preferred_currency": "INR",
        "travel_pace": "relaxed",
    }
    data.update(overrides)
    return data


class RegistrationTests(TestCase):
    def test_page_loads_with_all_fields(self):
        response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)
        for name in ["full_name", "email", "username", "password1", "password2", "home_city",
                     "preferred_currency", "travel_pace"]:
            self.assertContains(response, f'name="{name}"')
        self.assertContains(response, "data-chat")

    def test_registration_creates_user_and_profile_and_logs_in(self):
        response = self.client.post(reverse("signup"), registration())
        self.assertRedirects(response, reverse("planner:my_trips"))
        user = User.objects.get(username="kavya")
        self.assertEqual(user.email, "kavya.raman@example.com")
        self.assertEqual((user.first_name, user.last_name), ("Kavya", "Raman"))
        self.assertTrue(user.check_password("travel-Plans-2026"))
        profile = user.profile
        self.assertEqual((profile.full_name, profile.home_city, profile.preferred_currency, profile.travel_pace),
                         ("Kavya Raman", "Madurai", "INR", "relaxed"))
        self.assertFalse(profile.is_sample)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.id)

    def test_validation_errors(self):
        User.objects.create_user("taken", email="taken@example.com", password="x-Strong-pass-1")
        cases = {
            "email": registration(email="TAKEN@example.com"),       # duplicate email, any case
            "username": registration(username="taken"),            # duplicate username
            "password2": registration(password2="different-Pass-9"),
            "full_name": registration(full_name="12345"),
            "home_city": registration(home_city="!!!"),
            "preferred_currency": registration(preferred_currency="XYZ"),
        }
        for field, data in cases.items():
            response = self.client.post(reverse("signup"), data)
            self.assertEqual(response.status_code, 200, field)
            self.assertIn(field, response.context["form"].errors, field)
        self.assertFalse(User.objects.filter(username="kavya").exists())
        self.assertEqual(UserProfile.objects.count(), 0)

    def test_weak_password_rejected(self):
        response = self.client.post(reverse("signup"), registration(password1="password", password2="password"))
        self.assertIn("password2", response.context["form"].errors)

    def test_plan_form_prefilled_from_profile(self):
        self.client.post(reverse("signup"), registration(preferred_currency="EUR"))
        form = self.client.get(reverse("planner:plan")).context["form"]
        self.assertEqual(form["origin"].value(), "Madurai")
        self.assertEqual(form["currency"].value(), "EUR")
        self.assertEqual(form["pace"].value(), "relaxed")

    def test_users_without_profile_still_work(self):
        User.objects.create_user("legacy", password="x-Strong-pass-1")
        self.client.login(username="legacy", password="x-Strong-pass-1")
        self.assertEqual(self.client.get(reverse("planner:plan")).status_code, 200)


class SampleUserTests(TestCase):
    def test_seed_creates_five_users_with_login_disabled(self):
        call_command("seed_sample_users", verbosity=0)
        call_command("seed_sample_users", verbosity=0)  # idempotent
        samples = UserProfile.objects.filter(is_sample=True).select_related("user")
        self.assertEqual(samples.count(), 5)
        self.assertEqual({p.user.username for p in samples}, {u["username"] for u in SAMPLE_USERS})
        for profile in samples:
            self.assertFalse(profile.user.has_usable_password())
            self.assertFalse(profile.user.is_staff)
            self.assertTrue(profile.user.email.endswith("@example.com"))
            self.assertTrue(profile.home_city and profile.full_name)

    def test_retired_samples_removed_but_real_accounts_kept(self):
        old = User.objects.create_user("sample_meera", email="meera.nair@example.com")
        UserProfile.objects.create(user=old, full_name="Meera Nair", is_sample=True)
        real = User.objects.create_user("sample_fan", password="x-Strong-pass-1")  # real user, not a sample
        UserProfile.objects.create(user=real, full_name="Real Person")
        call_command("seed_sample_users", verbosity=0)
        self.assertFalse(User.objects.filter(username="sample_meera").exists())
        self.assertTrue(User.objects.filter(username="sample_fan").exists())
        mine = User.objects.get(username="sample_karthik")
        self.assertEqual((mine.profile.full_name, mine.email), ("Karthik Aravind M", "karthik.aravind@example.com"))

    def test_sample_users_cannot_log_in(self):
        call_command("seed_sample_users", verbosity=0)
        self.assertFalse(self.client.login(username="sample_priya", password=""))
        response = self.client.post(reverse("login"), {"username": "sample_priya", "password": "anything-at-all"})
        self.assertEqual(response.status_code, 200)  # login form re-shown with an error
        self.assertNotIn("_auth_user_id", self.client.session)
