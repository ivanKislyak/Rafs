from io import BytesIO
from uuid import uuid4

from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from django import forms
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import ModerationApplication

class RegisterUserForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.render_value = True
        self.fields["password2"].widget.render_value = True

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = UserCreationForm.Meta.fields + ("email",)


class AvatarUpdateForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ("avatar_image",)
        widgets = {
            "avatar_image": forms.FileInput(
                attrs={"accept": "image/*", "class": "profile-avatar-input"}
            )
        }

    def clean_avatar_image(self):
        uploaded_file = self.cleaned_data.get("avatar_image")
        if not uploaded_file:
            return uploaded_file

        if uploaded_file.size > 12 * 1024 * 1024:
            raise ValidationError(_("The image must be smaller than 12 MB."))

        try:
            uploaded_file.seek(0)
            with Image.open(uploaded_file) as source_image:
                image = ImageOps.exif_transpose(source_image)
                image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
                image = image.convert("RGBA" if has_alpha else "RGB")

                output = BytesIO()
                image.save(output, format="PNG", optimize=True)
        except (UnidentifiedImageError, OSError, ValueError):
            raise ValidationError(_("Upload a valid image file."))

        return ContentFile(
            output.getvalue(),
            name=f"avatar_{uuid4().hex}.png",
        )


class ModerationApplicationForm(forms.ModelForm):
    class Meta:
        model = ModerationApplication
        fields = ("email",)
        labels = {"email": _("Contact email")}
        widgets = {
            "email": forms.EmailInput(
                attrs={
                    "autocomplete": "email",
                    "placeholder": "name@example.com",
                }
            )
        }
