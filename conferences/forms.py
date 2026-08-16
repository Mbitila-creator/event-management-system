from django import forms
from django.core.exceptions import ValidationError

from .models import ConferencePaper, ConferencePaperReviewAssignment


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


class ConferencePeerReviewForm(forms.ModelForm):
    SCORE_CHOICES = (("", "Select score"),) + tuple(
        (value, f"{value} — {label}")
        for value, label in (
            (1, "Very weak"), (2, "Weak"), (3, "Adequate"),
            (4, "Strong"), (5, "Excellent"),
        )
    )

    class Meta:
        model = ConferencePaperReviewAssignment
        fields = (
            "status", "conflict_reason", "relevance_score", "originality_score",
            "methodology_score", "clarity_score", "impact_score", "recommendation",
            "comments_to_author", "confidential_comments",
        )
        widgets = {
            "conflict_reason": forms.Textarea(attrs={"rows": 3}),
            "comments_to_author": forms.Textarea(attrs={"rows": 6}),
            "confidential_comments": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in (
            "relevance_score", "originality_score", "methodology_score",
            "clarity_score", "impact_score",
        ):
            self.fields[name].widget = forms.Select(choices=self.SCORE_CHOICES)
        self.fields["status"].choices = (
            (ConferencePaperReviewAssignment.Status.IN_PROGRESS, "Save as in progress"),
            (ConferencePaperReviewAssignment.Status.COMPLETED, "Submit completed review"),
            (ConferencePaperReviewAssignment.Status.CONFLICT, "Declare conflict of interest"),
        )
