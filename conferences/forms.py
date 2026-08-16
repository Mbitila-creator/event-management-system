from django import forms
from django.core.exceptions import ValidationError

from .models import ConferencePaper


class ConferencePaperSubmissionForm(forms.ModelForm):
    confirmation = forms.BooleanField(
        label=(
            "I confirm that the information is correct and that all listed "
            "authors have agreed to this submission."
        ),
    )

    class Meta:
        model = ConferencePaper
        fields = (
            "submission_type",
            "presentation_format",
            "title",
            "abstract",
            "thematic_area",
            "keywords",
            "corresponding_author",
            "institution",
            "email",
            "phone",
            "co_authors",
            "document",
        )
        widgets = {
            "abstract": forms.Textarea(attrs={"rows": 9}),
            "co_authors": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {
            "abstract": "Provide a concise summary of the problem, methods, findings and contribution.",
            "keywords": "Separate keywords with commas.",
            "document": "Optional for an abstract; required for a full paper. PDF, DOC or DOCX, maximum 10 MB.",
        }

    def clean_abstract(self):
        abstract = self.cleaned_data["abstract"].strip()
        word_count = len(abstract.split())
        if word_count < 20:
            raise ValidationError("The abstract must contain at least 20 words.")
        if word_count > 1000:
            raise ValidationError("The abstract must not exceed 1,000 words.")
        return abstract
