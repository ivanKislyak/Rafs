"""Public SEO addresses are independent of Host, cookies and proxy headers."""

from urllib.parse import urlencode, urlsplit, urlunsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.templatetags.static import static
from django.utils.encoding import iri_to_uri

PUBLIC_ORIGIN = "https://rafs.app"
PUBLIC_DOMAIN = "rafs.app"
WEBSITE = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    "@id": PUBLIC_ORIGIN + "/#website",
    "name": "RAFS",
    "alternateName": ["Рафс", "rafs.app"],
    "url": PUBLIC_ORIGIN + "/",
}


def canonical_url(context):
    request = context.get("request")
    path = request.path if request is not None else "/"
    parameters = []
    match = getattr(request, "resolver_match", None)
    view_name = match.view_name if match else None
    if view_name == "movies:catalog":
        form = context.get("filter_form")
        if form is not None and form.is_valid():
            # Only filters actually used by the view; omit tracking, tokens,
            # email parameters, AJAX format and other arbitrary query data.
            for key in ("query", "min_rating", "year_from", "year_to"):
                value = form.cleaned_data.get(key)
                if value is not None and value != "":
                    parameters.append((key, str(value)))
    if view_name in {"movies:catalog", "movies:show_reviews"}:
        page = context.get("page_obj")
        # Use the resolved page, including Paginator's invalid/out-of-range
        # normalization. Page one has the clean URL; later pages self-canonicalize.
        if page is not None and page.number > 1:
            parameters.append(("page", page.number))
    query = "?" + urlencode(parameters) if parameters else ""
    return PUBLIC_ORIGIN + iri_to_uri("/" + path.lstrip("/")) + query


def public_image_url(value):
    """Absolute HTTPS OG images; reject unsupported schemes and credentials."""
    fallback = PUBLIC_ORIGIN + static("images/rafs-preview-v3.png")
    value = str(value or "").strip()
    if not value:
        return fallback
    if value.startswith("//"):
        value = "https:" + value
    elif value.startswith("/"):
        value = PUBLIC_ORIGIN + value
    try:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or parts.username or parts.password:
            return fallback
        URLValidator(schemes=["http", "https"])(value)
        return iri_to_uri(urlunsplit(("https", parts.netloc, parts.path, parts.query, "")))
    except (ValueError, ValidationError):
        return fallback
