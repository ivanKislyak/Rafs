from django.utils.translation import gettext as _
from rest_framework import serializers

from .models import Feedback


class FeedbackSerializer(serializers.ModelSerializer):
    message = serializers.CharField(min_length=10,max_length=2000)

    class Meta:
        model = Feedback
        fields = ["id", "kind", "message", "email", "page_url", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        request = self.context["request"]
        if not request.user.is_authenticated and not attrs["email"]:
            raise serializers.ValidationError(
                {"email": [_("To submit a request, you must either enter your email address or log in")]}
            )
        return attrs