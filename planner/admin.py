from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import Activity, Expense, ItineraryDay, Trip, UserProfile


class ItineraryDayInline(admin.TabularInline):
    model = ItineraryDay
    extra = 0
    fields = ("day_number", "date", "title", "estimated_cost")


class ExpenseInline(admin.TabularInline):
    model = Expense
    extra = 0


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ("destination", "start_date", "end_date", "travellers", "budget", "currency", "source", "user", "created_at")
    list_filter = ("source", "pace", "currency")
    search_fields = ("destination",)
    inlines = [ItineraryDayInline, ExpenseInline]


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("name", "day", "time_slot", "category", "cost_per_person", "is_completed", "is_removed")
    list_filter = ("category", "is_completed", "is_removed")


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    extra = 0


admin.site.unregister(User)


@admin.register(User)
class TripCraftUserAdmin(UserAdmin):
    inlines = [UserProfileInline]
    list_display = ("username", "email", "first_name", "last_name", "is_staff", "date_joined")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "home_city", "preferred_currency", "travel_pace", "is_sample", "created_at")
    list_filter = ("preferred_currency", "travel_pace", "is_sample")
    search_fields = ("full_name", "user__username", "user__email", "home_city")
