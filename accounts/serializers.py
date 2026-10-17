from rest_framework import serializers
from accounts.models import SearchHistory

class SearchHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SearchHistory
        fields = ('query', 'created_at')