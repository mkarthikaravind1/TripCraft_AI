from django.urls import path

from . import views

app_name = "support"

urlpatterns = [
    path("faq/", views.faq_page, name="faq"),
    path("support/tickets/new/", views.create_ticket, name="create_ticket"),
    path("support/tickets/<str:reference>/", views.ticket_detail, name="ticket_detail"),
    path("support/chat/", views.chat_message, name="chat"),
    path("support/chat/state/", views.chat_state, name="chat_state"),
    path("support/chat/ticket/", views.chat_ticket, name="chat_ticket"),
    path("support/chat/feedback/", views.chat_feedback, name="chat_feedback"),
    path("health/", views.health, name="health"),
    path("health/ready/", views.ready, name="ready"),
]
