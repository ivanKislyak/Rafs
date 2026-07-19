from django import forms

class MovieFilterForm(forms.Form):
    main_widget = forms.TextInput(attrs={"class": "filter-input", "placeholder": "Введите название...",})
    year_from_widget = forms.NumberInput(attrs={"class": "filter-input", "placeholder": "1888", })
    year_to_widget = forms.NumberInput(attrs={"class": "filter-input", "placeholder": "2026", })
    min_rate_widget = forms.NumberInput(attrs={"class": "filter-input", "placeholder": "0-10", })

    query = forms.CharField(required=False, min_length=2, max_length=80, help_text='Например, Fight Club', label='Название фильма', widget=main_widget)
    min_rating = forms.DecimalField(decimal_places=1, required=False, min_value=1.0, max_value=10.0, label='Рейтинг от', widget=min_rate_widget)
    year_from = forms.IntegerField(required=False, min_value=1888, max_value=2026, label='Год от', widget=year_from_widget)
    year_to = forms.IntegerField(required=False, min_value=1888, max_value=2026, label='Год до', widget=year_to_widget)

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
                '"Год до" не может быть меньше, чем "Год от".',
            )

        return cleaned_data