"""The "Liked Titles" playlist: one private Favourite playlist per user.

It is created on sign-up (movies/signals.py) and for existing users by the
0055_create_liked_titles migration. The heart buttons on movie covers add and
remove movies through the ordinary playlist item API.
"""
from ..models import LIKED_TITLES_NAME, KindChoice, Playlist


def ensure_liked_titles(user):
    """Return the user's Liked Titles playlist, creating it if it is missing."""
    # get_or_create re-reads the row if a concurrent request created it first
    # (the unique_favourite_playlist constraint allows only one per user).
    playlist, _ = Playlist.objects.get_or_create(
        owner=user,
        kind=KindChoice.FAVOURITE,
        defaults={"name": LIKED_TITLES_NAME, "is_public": False},
    )
    return playlist
