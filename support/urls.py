from django.urls import path

from . import views

app_name = "support"

urlpatterns = [
    # Pages
    path("faq/", views.faq_page, name="faq"),
    path("support/", views.support_page, name="support"),
    path("support/tickets/new/", views.create_ticket, name="create_ticket"),
    path("support/tickets/lookup/", views.lookup_ticket, name="lookup_ticket"),
    path("support/tickets/<str:reference>/", views.ticket_detail, name="ticket_detail"),
    path("support/tickets/<str:reference>/status/", views.ticket_status, name="ticket_status"),
    path("support/tickets/<str:reference>/delete/", views.ticket_delete, name="ticket_delete"),
    # Assistant
    path("support/chat/", views.chat_message, name="chat"),
    path("support/chat/state/", views.chat_state, name="chat_state"),
    path("support/chat/ticket/", views.chat_ticket, name="chat_ticket"),
    path("support/chat/feedback/", views.chat_feedback, name="chat_feedback"),
    # JSON API
    path("api/faqs/", views.faqs_api, name="api_faqs"),
    path("api/error-codes/", views.error_codes_api, name="api_error_codes"),
    path("api/tickets/", views.tickets_api, name="api_tickets"),
    path("api/tickets/lookup/", views.ticket_lookup_api, name="api_ticket_lookup"),
    path("api/tickets/<str:reference>/", views.ticket_api, name="api_ticket"),
    # Health
    path("health/", views.health, name="health"),
    path("health/ready/", views.ready, name="ready"),
]
