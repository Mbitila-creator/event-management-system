import csv
from io import BytesIO
from io import StringIO
from urllib.parse import urljoin

import qrcode
from django.conf import settings
from django.urls import reverse
from django.utils import timezone, translation

from .models import FormQuestion


def public_form_path(event_form, language="sw"):
    with translation.override(language):
        return reverse(
            "forms_builder:public_event_form",
            kwargs={
                "event_slug": event_form.event.slug,
                "form_slug": event_form.slug,
            },
        )


def public_form_url(event_form, request=None, language="sw"):
    path = public_form_path(event_form, language=language)
    base_url = settings.PUBLIC_BASE_URL

    if base_url:
        return urljoin(f"{base_url}/", path.lstrip("/"))

    if request is not None:
        return request.build_absolute_uri(path)

    return path


def generate_qr_png(value):
    qr_code = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr_code.add_data(value)
    qr_code.make(fit=True)

    image = qr_code.make_image(
        fill_color="#000000",
        back_color="#ffffff",
    )

    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def safe_spreadsheet_value(value):
    if value is None:
        return ""

    text = str(value)

    if text.lstrip().startswith(("=", "+", "-", "@")):
        return f"'{text}"

    return text


def answer_export_value(answer):
    selected_options = list(answer.selected_options.all())

    if selected_options:
        labels = [
            option.label_en
            if answer.submission.language == "en"
            else option.label_sw
            for option in selected_options
        ]
        return ", ".join(labels)

    if answer.uploaded_file:
        return answer.uploaded_file.url

    if answer.boolean_value is not None:
        if answer.submission.language == "en":
            return "Yes" if answer.boolean_value else "No"
        return "Ndiyo" if answer.boolean_value else "Hapana"

    for value in (
        answer.text_value,
        answer.number_value,
        answer.date_value,
        answer.datetime_value,
    ):
        if value not in (None, ""):
            return value

    return ""


def submissions_csv(submissions):
    submissions = list(submissions)
    form_ids = {item.event_form_id for item in submissions}
    questions = list(
        FormQuestion.objects.filter(
            section__event_form_id__in=form_ids,
        )
        .select_related("section__event_form__event")
        .order_by(
            "section__event_form_id",
            "section__display_order",
            "display_order",
            "id",
        )
    )

    output = StringIO()
    writer = csv.writer(output)
    fixed_headers = [
        "Reference Number",
        "Event",
        "Form",
        "Email",
        "Phone",
        "Language",
        "Complete",
        "Submitted On",
    ]
    question_headers = [
        f"{question.section.event_form.event.code} — {question.label_en}"
        for question in questions
    ]
    writer.writerow(fixed_headers + question_headers)

    for submission in submissions:
        answer_map = {
            answer.question_id: answer_export_value(answer)
            for answer in submission.answers.all()
        }
        submitted_on = timezone.localtime(
            submission.created_at
        ).strftime("%Y-%m-%d %H:%M:%S")
        fixed_values = [
            submission.reference_number,
            submission.event_form.event.code,
            submission.event_form.name_en,
            submission.submitter_email,
            submission.submitter_phone,
            submission.language,
            "Yes" if submission.is_complete else "No",
            submitted_on,
        ]
        question_values = [
            answer_map.get(question.id, "")
            if question.section.event_form_id == submission.event_form_id
            else ""
            for question in questions
        ]
        writer.writerow(
            [safe_spreadsheet_value(value) for value in fixed_values + question_values]
        )

    return output.getvalue()
