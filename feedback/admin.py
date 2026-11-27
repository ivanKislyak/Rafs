from django.contrib import admin

from .models import Feedback


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("kind", "email", "created_at", "is_resolved")
    list_filter = ("is_resolved",)
