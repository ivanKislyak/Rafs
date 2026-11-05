from rest_framework import serializers
from django.urls import reverse
from rest_framework.renderers import JSONRenderer
import io
from accounts.models import SearchHistory, User
from rest_framework.parsers import JSONParser


class SearchQueryField(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail('invalid')
        return super().to_internal_value(data)


class SearchHistorySerializer(serializers.ModelSerializer):
    query = SearchQueryField(max_length=SearchHistory._meta.get_field('query').max_length)

    class Meta:
        model = SearchHistory
        fields = "__all__"
        read_only_fields = ('user', 'updated_at', 'created_at')

class MeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'name', 'about', 'sex', 'bd_date']
        read_only_fields = ('id', 'username')

class UsernameSettingsSerializer(serializers.ModelSerializer):
    profile_url = serializers.SerializerMethodField()
    class Meta:
        model = User
        fields = ['username', 'profile_url']
    
    def get_profile_url(self, obj):
        return reverse('profile', kwargs={"username": obj.username})    
