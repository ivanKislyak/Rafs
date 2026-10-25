from django.core.exceptions import ObjectDoesNotExist
from django.templatetags.static import static
from django.urls import reverse
from django.utils.translation import gettext as _
from rest_framework import serializers

from .search_config import TITLE_FIELDS, DESCRIPTION_FIELDS, IMAGE_FIELDS

# Search Result Block
def _read(target, field):
    if hasattr(target, 'safe_translation_getter') and field in target._parler_meta.get_all_fields():
        return target.safe_translation_getter(field, any_language=True)
    return getattr(target, field, None)


class SearchResultSerializer(serializers.Serializer):
    id = serializers.IntegerField(source='object_id')
    type = serializers.CharField(source='content_type.model')
    wikidata_id = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    rank = serializers.FloatField(read_only=True)
    image = serializers.SerializerMethodField() 
    year = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()
    author = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(source='content_object.created_at', default=None, read_only=True)
    date_joined = serializers.SerializerMethodField()
    is_deleted = serializers.SerializerMethodField()

    def to_representation(self, instance):
        if instance.content_object is None:
            return None
        try:
            return super().to_representation(instance)
        except ObjectDoesNotExist:
            # A stale index entry or a related object removed during this request.
            return None

    def get_url(self, obj):
        target = obj.content_object
        model = obj.content_type.model
        if model == 'movie':
            return reverse('movies:detail', args=[target.pk])
        if model == 'review':
            return f"{reverse('movies:detail', args=[target.movie.pk])}#review-{target.pk}"
        if model == 'user' and not target.is_deleted:
            return reverse('profile', kwargs={'username': target.username})
        return None

    def get_author(self, obj):
        if obj.content_type.model != 'review':
            return None
        user = obj.content_object.user
        if user.is_deleted:
            return {'name': _('Deleted user'), 'url': None,
                    'image': static('images/default_profile_img.png'), 'is_deleted': True}
        avatar = user.avatar_image
        image = avatar.url if avatar and avatar.storage.exists(avatar.name) else static('images/default_profile_img.png')
        return {'name': user.username, 'url': reverse('profile', kwargs={'username': user.username}),
                'image': image, 'is_deleted': False}

    def get_date_joined(self, obj):
        user = obj.content_object
        if obj.content_type.model == 'user' and not user.is_deleted:
            return user.date_joined.isoformat()
        return None

    def get_is_deleted(self, obj):
        return obj.content_type.model == 'user' and obj.content_object.is_deleted

    def get_wikidata_id(self, obj):
        target = obj.content_object
        if target is None:
            return None
        return getattr(target, 'wikidata_id', None)

    def get_title(self, obj):
        target = obj.content_object
        if target is None:
            return None

        model = obj.content_type.model
        if model == 'review':
            target, model = target.movie, 'movie'
        elif model == 'user' and target.is_deleted:
            return None

        for field in TITLE_FIELDS.get(model, ()):
            value = _read(target, field)
            if value:
                return value

        return getattr(target, 'wikidata_id', None) or None
    
    def get_description(self, obj):
        target = obj.content_object
        if target is None:
            return None

        model = obj.content_type.model
        if model == 'user' and target.is_deleted:
            return None

        for field in DESCRIPTION_FIELDS.get(model, ()):
            value = _read(target, field)
            if value:
                return value

        return None

    def get_year(self, obj):
        target = obj.content_object
        return getattr(target, 'year', None) if target is not None else None

    def get_image(self, obj):
        target = obj.content_object
        if target is None:
            return None

        model = obj.content_type.model
        if model == 'review':
            target, model = target.movie, 'movie'
        elif model == 'user' and target.is_deleted:
            return None

        for field in IMAGE_FIELDS.get(model, ()):
            value = getattr(target, field, None)
            if not value:
                continue
            if isinstance(value, str):
                return value
            if value.storage.exists(value.name):
                return value.url

        if model == 'movie':
            return static('movies/images/nocover.png')
        elif model == 'user':
            return static('images/default_profile_img.png')
        else:
            return None

# Watch Status Block
class WatchStatusSerializer(serializers.ModelSerializer):
    class Meta:
        pass