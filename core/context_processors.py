from django.conf import settings


def site_event(request):
    """Expose the seasonal switch so templates skip event-only markup entirely."""
    return {"site_event": getattr(settings, "SITE_EVENT", "")}
