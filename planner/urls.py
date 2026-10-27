from django.urls import path

from . import views

app_name = "planner"

urlpatterns = [
    path("", views.home, name="home"),
    path("plan/", views.plan_trip, name="plan"),
    path("trips/", views.my_trips, name="my_trips"),
    path("trips/<uuid:trip_id>/", views.trip_detail, name="trip_detail"),
    path("trips/<uuid:trip_id>/regenerate/", views.regenerate_trip, name="regenerate"),
    path("trips/<uuid:trip_id>/delete/", views.delete_trip, name="delete"),
    path("trips/<uuid:trip_id>/weather/", views.trip_weather, name="trip_weather"),
    path("trips/<uuid:trip_id>/budget/", views.update_budget, name="update_budget"),
    path("trips/<uuid:trip_id>/activities/remove/", views.remove_activities, name="remove_activities"),
    path("trips/<uuid:trip_id>/activities/<int:activity_id>/", views.update_activity, name="update_activity"),
]
