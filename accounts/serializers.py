from rest_framework import serializers
from rest_framework.renderers import JSONRenderer
import io
from accounts.models import SearchHistory
from rest_framework.parsers import JSONParser


class SearchHistorySerializer(serializers.Serializer):
    user = serializers.CharField(source='user.username', read_only=True)
    query = serializers.CharField(max_length=200)
    created_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = SearchHistory
        fields = ['user', 'query', 'created_at']