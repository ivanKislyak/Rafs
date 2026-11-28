from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import NotificationSerializer


class NotificationListAPIView(APIView):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        notifications = Notification.objects.select_related('actor', 'review').filter(recipient=request.user)
        serializer = self.serializer_class(
            notifications,
            many=True,
            context={"request": request}
        )
        return Response(data=serializer.data, status=status.HTTP_200_OK)

class UnreadCountAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(
            data={
                "unread": Notification.objects.filter(
                    recipient=request.user, is_read=False).count()
                }, 
            status=status.HTTP_200_OK)

class MarkAllReadAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response(status=status.HTTP_204_NO_CONTENT)
