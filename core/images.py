"""Downscale uploaded raster images to twice their largest on-screen size and
re-encode them in a lossy format. Shared by upload paths and optimize_media."""
import re
from io import BytesIO

from PIL import Image, ImageOps, PngImagePlugin

# Some covers carry megabytes of PNG text metadata; we drop it on re-encode anyway.
PngImagePlugin.MAX_TEXT_CHUNK = 64 * 1024 * 1024

# Largest CSS display size x2 (retina).
AVATAR_SIZE = (224, 224)       # .profile-avatar is 112px
MOVIE_COVER_SIZE = (540, 810)  # catalogue cards reach ~270px wide (2:3)

QUALITY = 82


def _prepare(source, box):
    image = ImageOps.exif_transpose(source)
    image.thumbnail(box, Image.Resampling.LANCZOS)
    has_alpha = image.mode in {"RGBA", "LA", "PA"} or "transparency" in image.info
    return image.convert("RGBA" if has_alpha else "RGB"), has_alpha


def encode_webp(source, box):
    """Avatars may be transparent, so WebP (lossy, keeps alpha)."""
    image, _ = _prepare(source, box)
    output = BytesIO()
    image.save(output, format="WEBP", quality=QUALITY, method=6)
    return output.getvalue()


def encode_jpeg(source, box, background=(255, 255, 255)):
    """Posters are opaque photos; JPEG also keeps og:image previews universal."""
    image, has_alpha = _prepare(source, box)
    if has_alpha:
        flat = Image.new("RGB", image.size, background)
        flat.paste(image, mask=image.getchannel("A"))
        image = flat
    output = BytesIO()
    image.save(output, format="JPEG", quality=QUALITY, optimize=True, progressive=True)
    return output.getvalue()


_TMDB_POSTER = re.compile(r"^(https?://image\.tmdb\.org/t/p/)[^/]+/")


def tmdb_poster(url, size="w500"):
    """Ask TMDB for a rendition sized to the slot (w154, w342, w500, ...)."""
    url = str(url or "")
    return _TMDB_POSTER.sub(lambda m: f"{m.group(1)}{size}/", url, count=1)
