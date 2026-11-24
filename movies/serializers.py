from django.core.exceptions import ObjectDoesNotExist
from django.templatetags.static import static
from django.urls import reverse
from django.utils.translation import get_language, gettext as _
from rest_framework import serializers

from core.images import tmdb_poster

from .search_config import TITLE_FIELDS, DESCRIPTION_FIELDS, IMAGE_FIELDS
from .models import (
    WatchStatus, ReviewReply, Playlist, PlaylistItem, Movie, SavedPlaylist,
    PLAYLIST_NAME_MAX_LENGTH,
)

# Search Result Block
def _read(target, field):
    if hasattr(target, 'safe_translation_getter') and field in target._parler_meta.get_all_fields():
        return target.safe_translation_getter(field, any_language=True)
    return getattr(target, field, None)


class SearchResultSerializer(serializers.Serializer):
    """
    Serializes a GlobalSearchIndex entry into a uniform search result.

    The index points to different models (movie, review, person, studio,
    user, country, genre, typeofwork, playlist) through a generic relation, so every
    result is flattened into the same set of fields: id, type, title,
    description, image, url, etc.

    Rules:
    - Titles, descriptions and images are looked up through the
      TITLE_FIELDS / DESCRIPTION_FIELDS / IMAGE_FIELDS maps, using the
      first non-empty field of the target model.
    - A review is shown with the title and image of its movie and gets an
      extra `author` block.
    - Deleted users expose no personal data (title, description, image).
    - Stale entries, where the indexed object no longer exists, are
      serialized as None.
    """

    id = serializers.SerializerMethodField()
    type = serializers.CharField(source='content_type.model')
    type_of_work = serializers.SerializerMethodField()
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

    def get_id(self, obj):
        # Playlists are public by external_id only; their pk stays internal.
        if obj.content_type.model == 'playlist':
            return obj.content_object.external_id
        return obj.object_id

    def get_url(self, obj):
        target = obj.content_object
        model = obj.content_type.model
        if model == 'movie':
            return reverse('movies:detail', args=[target.pk])
        if model == 'review':
            return f"{reverse('movies:detail', args=[target.movie.pk])}#review-{target.pk}"
        if model == 'user' and not target.is_deleted:
            return reverse('profile', kwargs={'username': target.username})
        if model == 'playlist':
            return reverse('movies:playlist', args=[target.external_id])
        return None

    def get_type_of_work(self, obj):
        if obj.content_type.model != 'movie':
            return None
        work_type = obj.content_object.type_of_work
        if work_type is None:
            return None
        return work_type.safe_translation_getter(
            'name', language_code=get_language(), any_language=True,
        ) or None

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
        if model == 'playlist':
            return f"@{target.owner.username}"

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
                # Search covers are 112px wide; w342 is the smallest TMDB size >= 2x.
                return tmdb_poster(value, 'w342') if model == 'movie' else value
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
    """
    Serializer for the WatchStatus model.

    Exposes only the `status` field, which is required on input.
    Used to validate and represent a watch status value (e.g. when
    creating or updating a user's status for a film).
    """

    class Meta:
        model = WatchStatus
        fields = ['status']
        extra_kwargs = {'status': {'required': True}}


class ReviewReplySerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewReply
        fields = ['id', 'user', 'review', 'text', 'created_at']
        read_only_fields = ['id', 'user', 'created_at', 'review']

class MovieSerializer(serializers.ModelSerializer):
    # title = SerializerMethodField()
    class Meta:
        model = Movie
        fields = ['id', 'name', 'year', 'tmdb_popularity', 'cover_url', 'cover']

class PlaylistItemSerializer(serializers.ModelSerializer):
    movie = MovieSerializer(read_only=True)
    class Meta:
        model = PlaylistItem
        fields = ['id', 'position', 'added_at', 'movie']

class PlaylistSerializer(serializers.ModelSerializer):
    name = serializers.CharField(max_length=PLAYLIST_NAME_MAX_LENGTH)
    id = serializers.CharField(source='external_id', read_only=True)
    items = PlaylistItemSerializer(many=True, read_only=True)
    class Meta:
        model = Playlist
        fields = ['id', 'name', 'kind', 'owner', 'cover', 'is_public', 'items']
        read_only_fields = ['kind', 'owner']

class PlaylistShortSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='external_id', read_only=True)
    movies_count = serializers.IntegerField(read_only=True)
    contains_movie = serializers.SerializerMethodField()

    class Meta:
        model = Playlist
        fields = ['id', 'name', 'kind', 'is_public', 'movies_count', 'contains_movie']

    def get_contains_movie(self, obj):
        return getattr(obj, 'contains_movie', None)


class LibraryPlaylistSerializer(serializers.ModelSerializer): 
    id = serializers.CharField(source='playlist.external_id', read_only=True)
    name = serializers.CharField(read_only=True)
    owner_username = serializers.CharField(read_only=True)
    movies_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = SavedPlaylist
        fields = ['id', 'name', 'owner_username', 'movies_count', 'saved_at']

class PlaylistOrderSerializer(serializers.Serializer):
    movie_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False, max_length=54000)
    
    def validate_movie_ids(self, movie_ids):
        if len(set(movie_ids)) != len(movie_ids):
            raise serializers.ValidationError(_("The problem lies in value passing"))
        return movie_ids

