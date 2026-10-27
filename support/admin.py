from django.contrib import admin

from .models import FAQ, SupportTicket


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ("question", "category", "order", "is_active", "updated_at")
    list_filter = ("category", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("question", "answer", "keywords")


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ("reference", "subject", "status", "priority", "error_code", "channel", "created_at")
    list_filter = ("status", "priority", "channel", "error_code")
    list_editable = ("status", "priority")
    search_fields = ("reference", "subject", "description")
    readonly_fields = ("reference", "session_key", "conversation_id", "created_at", "updated_at")
