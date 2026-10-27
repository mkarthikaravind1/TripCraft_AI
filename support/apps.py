from django.apps import AppConfig


class SupportConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "support"
    verbose_name = "TripCraft help & support"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        def attach_tickets(sender, request, user, **kwargs):
            from .models import SupportTicket
            from .services.tickets import SESSION_KEY

            if request is not None and request.session.get(SESSION_KEY):
                SupportTicket.objects.filter(reference__in=request.session[SESSION_KEY], user__isnull=True).update(user=user)

        user_logged_in.connect(attach_tickets, dispatch_uid="support_claim_session_tickets", weak=False)
