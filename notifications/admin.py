from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "kind", "actor", "amount", "is_read", "created_at")
    list_filter = ("kind", "is_read")
    search_fields = ("recipient__username",)
    raw_id_fields = ("recipient", "actor", "review")
