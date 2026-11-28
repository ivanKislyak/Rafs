from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path('api/v1/notifications/', views.NotificationListAPIView.as_view(), name='list_api'),
    path('api/v1/notifications/unread-count/', views.UnreadCountAPIView.as_view(), name='unread_count_api'),
    path('api/v1/notifications/read/', views.MarkAllReadAPIView.as_view(), name='mark_read_api'),
]
