from django.contrib import admin
from .models import SearchHistory

@admin.register(SearchHistory)
class SearchHistoryAdmin(admin.ModelAdmin):
    list_display = ["id", "get_username", "query", "created_at"]
    list_select_related = ('user',)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "user":
            formfield.label_from_instance = lambda obj: obj.username
        return formfield

    @admin.display(description='User', ordering='user__username')
    def get_username(self, obj):
        return obj.user.username