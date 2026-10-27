from django.contrib import admin

from .models import Activity, Expense, ItineraryDay, Trip


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
