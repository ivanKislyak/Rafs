from rest_framework import serializers
from rest_framework.renderers import JSONRenderer
import io
from accounts.models import SearchHistory
from rest_framework.parsers import JSONParser


class SearchHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SearchHistory
        fields = "__all__"
        read_only_fields = ('user', 'created_at')