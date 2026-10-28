from django.contrib import admin
from .models import SearchHistory, User, Achievement, UserAchievement

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ["id", "username", 'email', 'date_joined', "user_lvl", "user_frames", 'is_deleted'] 
    

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

@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'avatar_image', 'display_in_profile']
    list_editable = ['display_in_profile']


@admin.register(UserAchievement)
class UserAchievementAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'achievement', 'earned_at']
    search_fields = ['user__username', 'achievement__name', 'achievement__code']
    list_filter = ['earned_at']
    list_select_related = ('user', 'achievement')
    raw_id_fields = ('user', 'achievement', 'source_review')
    readonly_fields = ('earned_at',)