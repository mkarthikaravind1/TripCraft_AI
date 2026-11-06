from django.contrib import messages
from django.contrib.auth import login
from django.db import transaction
from django.shortcuts import redirect, render

from planner.forms import SignUpForm
from planner.services import trips


def signup(request):
    if request.user.is_authenticated:
        return redirect("planner:my_trips")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():  # the user and their profile are saved together or not at all
            user = form.save()
        trips.claim_session_trips(request, user)
        login(request, user)
        first_name = user.first_name or user.username
        messages.success(request, f"Welcome to TripCraft AI, {first_name}! Trips from this browser are now saved to your account.")
        return redirect("planner:my_trips")
    return render(request, "registration/signup.html", {"form": form})
