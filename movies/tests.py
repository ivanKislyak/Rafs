from django.test import SimpleTestCase

from .forms import ReviewForm


class ReviewFormTests(SimpleTestCase):
    def test_review_form_contains_expected_fields(self):
        form = ReviewForm()

        self.assertIn("rating", form.fields)
        self.assertIn("text", form.fields)
        self.assertIn("contains_spoiler", form.fields)
