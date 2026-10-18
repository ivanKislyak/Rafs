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
        
    # def create(self, validated_data):
    #     user = self.context['request'].user
    #     return SearchHistory.objects.create(user=user, **validated_data)

    # def update(self, instance, validated_data):
    #     instance.query = validated_data.get('query', instance.query)
    #     instance.save()
        
    #     return instance

    # class Meta:
    #     model = SearchHistory
    #     fields = ['user', 'query', 'created_at']