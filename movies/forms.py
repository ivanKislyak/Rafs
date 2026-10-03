from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Review as ReviewModel, ReviewReply


class RatingRangeInput(forms.NumberInput):
    input_type = "range"


RATING_RANGE_ATTRS = {
    "class": "category-range form-range",
    "min": "0.0",
    "max": "10.0",
    "step": "0.1",
}

OPTIONAL_RATING_RANGE_ATTRS = {
    **RATING_RANGE_ATTRS,
    "disabled": True,
}

LANG_CHOICES = (
        ('en', 'English'),
        ('ru', 'Русский'),
        ('uk', 'Українська'),
        ('kk', 'Қазақша'),
        ('es', 'Español'),
    )

class MovieFilterForm(forms.Form):
    main_widget = forms.TextInput(
        attrs={"class": "filter-input", "placeholder": _("Enter a title...")}
    )
    year_from_widget = forms.NumberInput(attrs={"class": "filter-input", "placeholder": "1888", })
    year_to_widget = forms.NumberInput(attrs={"class": "filter-input", "placeholder": "2026", })
    min_rate_widget = forms.NumberInput(attrs={"class": "filter-input", "placeholder": "0-10", })

    query = forms.CharField(required=False, min_length=2, max_length=80, help_text=_("For example, Fight Club"), label=_("Movie title"), widget=main_widget)
    min_rating = forms.DecimalField(decimal_places=1, required=False, min_value=1.0, max_value=10.0, label=_("Minimum rating"), widget=min_rate_widget)
    year_from = forms.IntegerField(required=False, min_value=1888, max_value=2026, label=_("Year from"), widget=year_from_widget)
    year_to = forms.IntegerField(required=False, min_value=1888, max_value=2026, label=_("Year to"), widget=year_to_widget)

    def clean(self):
        cleaned_data = super().clean()

        year_from = cleaned_data.get("year_from")
        year_to = cleaned_data.get("year_to")

        if (
                year_from is not None
                and year_to is not None
                and year_to < year_from
        ):
            self.add_error(
                "year_to",
                _("Year to cannot be earlier than year from."),
            )

        return cleaned_data


class ReviewForm(forms.ModelForm):
    OPTIONAL_RATING_FIELDS = (
        ("idea_rating", "use_idea_rating"),
        ("execution_rating", "use_execution_rating"),
        ("characters_rating", "use_characters_rating"),
        ("sound_rating", "use_sound_rating"),
    )

    use_idea_rating = forms.BooleanField(
        required=False,
        label=_("Include"),
        widget=forms.CheckboxInput(
            attrs={
                "class": "review-rating-toggle-input",
                "aria-controls": "id_idea_rating",
            }
        ),
    )
    use_execution_rating = forms.BooleanField(
        required=False,
        label=_("Include"),
        widget=forms.CheckboxInput(
            attrs={
                "class": "review-rating-toggle-input",
                "aria-controls": "id_execution_rating",
            }
        ),
    )
    use_characters_rating = forms.BooleanField(
        required=False,
        label=_("Include"),
        widget=forms.CheckboxInput(
            attrs={
                "class": "review-rating-toggle-input",
                "aria-controls": "id_characters_rating",
            }
        ),
    )
    use_sound_rating = forms.BooleanField(
        required=False,
        label=_("Include"),
        widget=forms.CheckboxInput(
            attrs={
                "class": "review-rating-toggle-input",
                "aria-controls": "id_sound_rating",
            }
        ),
    )

    class Meta:
        model = ReviewModel
        fields = [
            "rating",
            "idea_rating",
            "execution_rating",
            "characters_rating",
            "sound_rating",
            "text",
            "contains_spoiler",
        ]
        labels = {
            "rating": _("Overall impression"),
            "idea_rating": _("Concept"),
            "execution_rating": _("Execution"),
            "characters_rating": _("Characters"),
            "sound_rating": _("Sound design"),
            "text": _("Review text"),
            "contains_spoiler": _("Contains spoilers"),
        }
        help_texts = {
            "rating": _("The overall rating is required. Other criteria are optional."),
            "text": _("Share your impressions of the movie"),
        }
        widgets = {
            "rating": RatingRangeInput(attrs=RATING_RANGE_ATTRS),
            "idea_rating": RatingRangeInput(attrs=OPTIONAL_RATING_RANGE_ATTRS),
            "execution_rating": RatingRangeInput(attrs=OPTIONAL_RATING_RANGE_ATTRS),
            "characters_rating": RatingRangeInput(attrs=OPTIONAL_RATING_RANGE_ATTRS),
            "sound_rating": RatingRangeInput(attrs=OPTIONAL_RATING_RANGE_ATTRS),
            "text": forms.Textarea(
                attrs={
                    "class": "review-input review-textarea",
                    "rows": 5,
                    "placeholder": _("Your opinion of the movie..."),
                }
            ),
            "contains_spoiler": forms.CheckboxInput(attrs={"class": "review-checkbox"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.is_bound and self.instance.pk:
            for rating_name, toggle_name in self.OPTIONAL_RATING_FIELDS:
                self.fields[toggle_name].initial = (
                    getattr(self.instance, rating_name) is not None
                )

    @property
    def optional_ratings(self):
        return [
            (self[rating_name], self[toggle_name])
            for rating_name, toggle_name in self.OPTIONAL_RATING_FIELDS
        ]

    def clean(self):
        cleaned_data = super().clean()

        for rating_name, toggle_name in self.OPTIONAL_RATING_FIELDS:
            if not cleaned_data.get(toggle_name):
                cleaned_data[rating_name] = None

        return cleaned_data


class ReviewReplyForm(forms.ModelForm):
    class Meta:
        model = ReviewReply
        fields = ["text"]

class WikidataSearchForm(forms.Form):
    query = forms.CharField(required=True, min_length=2, max_length=200)
    lang = forms.ChoiceField(choices=LANG_CHOICES)
