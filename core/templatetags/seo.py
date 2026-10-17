import json

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from core.seo import WEBSITE, canonical_url, public_image_url

register = template.Library()
register.simple_tag(canonical_url, takes_context=True)
register.filter("public_image_url", public_image_url)


@register.simple_tag
def website_json_ld():
    # No user/context values: serialize the single static WebSite object.
    # Escape script delimiters as JSON Unicode escapes, not HTML entities.
    payload = json.dumps(WEBSITE, ensure_ascii=True).translate({
        ord("<"): r"\u003C", ord(">"): r"\u003E", ord("&"): r"\u0026",
    })
    return format_html('<script type="application/ld+json">{}</script>', mark_safe(payload))
