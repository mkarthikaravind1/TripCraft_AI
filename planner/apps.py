from django.apps import AppConfig


class PlannerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "planner"
    verbose_name = "TripCraft planner"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        from .services.trips import claim_session_trips

        def attach_trips(sender, request, user, **kwargs):
            if request is not None:
                claim_session_trips(request, user)

        user_logged_in.connect(attach_trips, dispatch_uid="planner_claim_session_trips", weak=False)
