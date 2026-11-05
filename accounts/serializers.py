from rest_framework import serializers
from django.urls import reverse
import logging
from django.db import DatabaseError, IntegrityError, transaction
from django.utils.translation import gettext as _
from PIL import Image
from accounts.forms import AvatarUpdateForm
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


class ProfileSettingsSerializer(serializers.ModelSerializer):
    """Validate the entire staged profile before writing any field or file."""
    profile_url = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    has_avatar = serializers.SerializerMethodField()
    avatar_image = serializers.FileField(write_only=True, required=False)
    avatar_action = serializers.ChoiceField(choices=('keep', 'upload', 'remove'), write_only=True, required=False)

    class Meta:
        model = User
        fields = ('name', 'username', 'about', 'sex', 'bd_date', 'profile_url', 'avatar_url', 'has_avatar', 'avatar_image', 'avatar_action')

    get_profile_url = UsernameSettingsSerializer.get_profile_url

    def get_avatar_url(self, obj):
        from django.templatetags.static import static
        return obj.avatar_image.url if obj.avatar_image else static('images/default_profile_img.png')

    def get_has_avatar(self, obj):
        return bool(obj.avatar_image)

    def validate_avatar_image(self, value):
        # A separate instance prevents ModelForm validation mutating request.user.
        form = AvatarUpdateForm(files={'avatar_image': value}, instance=User())
        if not form.is_valid():
            raise serializers.ValidationError(form.errors['avatar_image'])
        image = form.cleaned_data['avatar_image']
        with Image.open(image) as source:
            if source.width != source.height:
                raise serializers.ValidationError(_('Choose a square avatar'))
        image.seek(0)
        return image

    def validate(self, attrs):
        action = attrs.get('avatar_action', 'keep')
        if (action == 'upload') != ('avatar_image' in attrs):
            raise serializers.ValidationError({'avatar_image': _('Confirm avatar cropping before saving')})
        return attrs

    def update(self, instance, validated_data):
        action = validated_data.pop('avatar_action', 'keep')
        image = validated_data.pop('avatar_image', None)
        storage = instance.avatar_image.storage
        old_name = instance.avatar_image.name
        fields = list(validated_data)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if action != 'keep':
            instance.avatar_image = image if action == 'upload' else None
            fields.append('avatar_image')

        def remove_old():
            try:
                storage.delete(old_name)
            except OSError:
                logging.getLogger(__name__).warning('Unable to remove replaced avatar', exc_info=True)

        try:
            with transaction.atomic():
                if fields:
                    instance.save(update_fields=fields)
                if old_name and old_name != instance.avatar_image.name:
                    transaction.on_commit(remove_old)
        except (DatabaseError, OSError) as error:
            avatar = instance.avatar_image
            if image and avatar.name != old_name and avatar._committed:
                storage.delete(avatar.name)
            if isinstance(error, IntegrityError) and User.objects.filter(username=instance.username).exclude(pk=instance.pk).exists():
                raise serializers.ValidationError({'username': _('A user with that username already exists.')}) from error
            raise
        return instance


class EmailSettingsSerializer(serializers.ModelSerializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = User
        fields = ('email', 'current_password')

    def validate(self, attrs):
        if not self.instance.check_password(attrs.get('current_password', '')):
            raise serializers.ValidationError({'current_password': _('Incorrect password')})
        if 'email' not in attrs:
            raise serializers.ValidationError({'email': _('This field is required.')})
        return attrs

    def update(self, instance, validated_data):
        instance.email = validated_data['email']
        try:
            with transaction.atomic():
                instance.save(update_fields=['email'])
        except IntegrityError as error:
            if User.objects.filter(email=instance.email).exclude(pk=instance.pk).exists():
                raise serializers.ValidationError({'email': _('This email address is already in use')}) from error
            raise
        return instance
