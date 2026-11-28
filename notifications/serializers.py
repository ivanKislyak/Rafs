from rest_framework import serializers

from .models import Notification

class NotificationSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source='actor.username', allow_null=True, read_only=True)
    review_id = serializers.IntegerField(source='review.id', allow_null=True, read_only=True)
    movie_id = serializers.IntegerField(source='review.movie_id', allow_null=True, read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'kind', 'is_read', 'created_at',
            'actor_username', 'review_id', 'movie_id',
            'amount',
        ]
