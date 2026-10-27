from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect, render

from planner.forms import SignUpForm
from planner.services import trips


def signup(request):
    if request.user.is_authenticated:
        return redirect("planner:my_trips")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        trips.claim_session_trips(request, user)
        login(request, user)
        messages.success(request, "Welcome to TripCraft AI! Trips from this browser are now saved to your account.")
        return redirect("planner:my_trips")
    return render(request, "registration/signup.html", {"form": form})
