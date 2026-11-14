from django import template

from core.images import tmdb_poster

register = template.Library()


@register.filter
def poster_size(url, size="w500"):
    """{{ movie.cover_url|poster_size:"w154" }}; non-TMDB URLs pass through."""
    return tmdb_poster(url, size)
