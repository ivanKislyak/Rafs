from django.urls import reverse


def url_template(viewname, **placeholders):
    """Reverse ``viewname`` with text placeholders in place of integer kwargs.

    ``url_template("movies:playlist", pl_id="__ID__")`` -> "/movies/playlist/__ID__/".
    Each kwarg is reversed as a distinct sentinel number that is then swapped
    for its placeholder, so the result follows the real URLconf.
    """
    sentinels = {name: 900_000_001 + index for index, name in enumerate(placeholders)}
    url = reverse(viewname, kwargs=sentinels)
    for name, placeholder in placeholders.items():
        url = url.replace(f"/{sentinels[name]}/", f"/{placeholder}/")
    return url
