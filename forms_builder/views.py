import csv
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import user_passes_test
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from accounts.models import User
from .models import (
    EventForm,
    FormAnswer,
    FormQuestion,
    FormSubmission,
    QuestionOption,
)
from .services import (
    certificate_number,
    certificate_verification_url,
    event_date_range,
    generate_certificate_pdf,
    generate_qr_png,
    participant_check_in_url,
    sync_badge_identity_from_answers,
    safe_spreadsheet_value,
)


EVALUATION_REPORT_ROLES = {
    User.Role.SYSTEM_ADMIN,
    User.Role.EVENT_ADMIN,
    User.Role.REPORT_OFFICER,
}


def can_view_evaluation_reports(user):
    return bool(
        user.is_authenticated
        and (
            user.is_superuser
            or user.role in EVALUATION_REPORT_ROLES
        )
    )


evaluation_report_required = user_passes_test(
    can_view_evaluation_reports,
    login_url="admin:login",
)


def localized_answer_value(answer, language):
    selected_options = list(answer.selected_options.all())
    if selected_options:
        return ", ".join(
            option.label_en if language == "en" else option.label_sw
            for option in selected_options
        )
    if answer.uploaded_file:
        return answer.uploaded_file.url
    if answer.text_value:
        return answer.text_value
    if answer.number_value is not None:
        return str(answer.number_value)
    if answer.date_value:
        return answer.date_value.isoformat()
    if answer.datetime_value:
        return answer.datetime_value.isoformat()
    if answer.boolean_value is not None:
        return _("Yes") if answer.boolean_value else _("No")
    return ""


def numeric_rating_value(answer):
    value = answer.number_value
    if value is None:
        selected_options = list(answer.selected_options.all())
        if len(selected_options) == 1:
            try:
                value = Decimal(selected_options[0].value)
            except (InvalidOperation, TypeError, ValueError):
                value = None
    if value is not None and Decimal("1") <= value <= Decimal("5"):
        return value
    return None


def get_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")

    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR")


def evaluation_forms_queryset():
    return EventForm.objects.filter(
        form_type=EventForm.FormType.EVALUATION,
        is_active=True,
    ).select_related("event").order_by("-event__starts_at", "name_en")


@evaluation_report_required
@require_http_methods(["GET"])
def evaluation_reports(request):
    evaluation_forms = evaluation_forms_queryset()
    selected_form_id = request.GET.get("form", "").strip()
    selected_form = (
        get_object_or_404(evaluation_forms, pk=selected_form_id)
        if selected_form_id
        else evaluation_forms.first()
    )
    questions = []
    response_rows = []
    rating_statistics = []
    total_responses = 0
    overall_average = None

    if selected_form:
        questions = list(
            FormQuestion.objects.filter(
                section__event_form=selected_form,
                section__is_active=True,
                is_active=True,
            ).select_related("section").order_by(
                "section__display_order",
                "display_order",
                "id",
            )
        )
        submissions = list(
            FormSubmission.objects.filter(
                event_form=selected_form,
                is_active=True,
                is_complete=True,
            ).prefetch_related(
                "answers__question",
                "answers__selected_options",
            ).order_by("-created_at")
        )
        total_responses = len(submissions)
        rating_values = {question.pk: [] for question in questions}

        for submission in submissions:
            answers_by_question = {
                answer.question_id: answer
                for answer in submission.answers.all()
            }
            row_answers = []
            for question in questions:
                answer = answers_by_question.get(question.pk)
                row_answers.append(
                    localized_answer_value(answer, request.LANGUAGE_CODE)
                    if answer
                    else ""
                )
                if answer:
                    rating_value = numeric_rating_value(answer)
                    if rating_value is not None:
                        rating_values[question.pk].append(rating_value)
            response_rows.append(
                {"submission": submission, "answers": row_answers}
            )

        all_ratings = []
        for question in questions:
            values = rating_values[question.pk]
            if values:
                average = sum(values) / len(values)
                all_ratings.extend(values)
                rating_statistics.append(
                    {
                        "label": (
                            question.label_en
                            if request.LANGUAGE_CODE == "en"
                            else question.label_sw
                        ),
                        "average": round(average, 2),
                        "count": len(values),
                    }
                )
        if all_ratings:
            overall_average = round(
                sum(all_ratings) / len(all_ratings),
                2,
            )

    return render(
        request,
        "forms_builder/evaluation_reports.html",
        {
            "evaluation_forms": evaluation_forms,
            "selected_form": selected_form,
            "questions": questions,
            "response_rows": response_rows,
            "rating_statistics": rating_statistics,
            "total_responses": total_responses,
            "overall_average": overall_average,
        },
    )


@evaluation_report_required
@require_http_methods(["GET"])
def evaluation_report_csv(request):
    selected_form = get_object_or_404(
        evaluation_forms_queryset(),
        pk=request.GET.get("form"),
    )
    questions = list(
        FormQuestion.objects.filter(
            section__event_form=selected_form,
            section__is_active=True,
            is_active=True,
        ).order_by(
            "section__display_order",
            "display_order",
            "id",
        )
    )
    submissions = FormSubmission.objects.filter(
        event_form=selected_form,
        is_active=True,
        is_complete=True,
    ).prefetch_related(
        "answers__question",
        "answers__selected_options",
    ).order_by("created_at")

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response.write("\ufeff")
    response["Content-Disposition"] = (
        f'attachment; filename="{selected_form.event.code}-evaluation.csv"'
    )
    writer = csv.writer(response)
    question_labels = [
        question.label_en
        if request.LANGUAGE_CODE == "en"
        else question.label_sw
        for question in questions
    ]
    writer.writerow(
        [
            _("Evaluation reference"),
            _("Submitted on"),
            _("Language"),
            _("Email address"),
            _("Phone number"),
            *question_labels,
        ]
    )
    for submission in submissions:
        answers_by_question = {
            answer.question_id: answer
            for answer in submission.answers.all()
        }
        values = [
            submission.reference_number,
            submission.created_at.isoformat(),
            submission.language,
            submission.submitter_email,
            submission.submitter_phone,
        ]
        values.extend(
            localized_answer_value(
                answers_by_question.get(question.pk),
                request.LANGUAGE_CODE,
            )
            if answers_by_question.get(question.pk)
            else ""
            for question in questions
        )
        writer.writerow([safe_spreadsheet_value(value) for value in values])
    return response


def get_public_event_form(event_slug, form_slug):
    event_form = get_object_or_404(
        EventForm.objects.select_related(
            "event",
            "event__category",
            "event__venue",
            "event__venue__council",
            "event__venue__council__region",
        ).prefetch_related(
            "sections__questions__options",
        ),
        event__slug=event_slug,
        slug=form_slug,
        event__is_active=True,
        event__is_public=True,
        is_active=True,
        is_published=True,
    )
    is_evaluation = event_form.form_type == EventForm.FormType.EVALUATION
    form_enabled = (
        event_form.event.evaluation_enabled
        if is_evaluation
        else event_form.event.registration_enabled
    )
    if not form_enabled:
        raise Http404("This public form is not enabled.")

    return event_form


def form_availability(event_form):
    current_time = timezone.now()

    form_not_open = (
        event_form.opens_at
        and current_time < event_form.opens_at
    )

    form_closed = (
        event_form.closes_at
        and current_time > event_form.closes_at
    )

    return form_not_open, form_closed


def validate_question_answer(request, question):
    field_name = f"question_{question.id}"
    question_type = question.question_type

    if question_type == FormQuestion.QuestionType.MULTIPLE_CHOICE:
        raw_value = request.POST.getlist(field_name)
    elif question_type in {
        FormQuestion.QuestionType.FILE,
        FormQuestion.QuestionType.IMAGE,
    }:
        raw_value = request.FILES.get(field_name)
    else:
        raw_value = request.POST.get(field_name, "").strip()

    is_empty = (
        raw_value is None
        or raw_value == ""
        or raw_value == []
    )

    if question.is_required and is_empty:
        return None, "This field is required."

    if is_empty:
        return {
            "question": question,
            "empty": True,
        }, None

    result = {
        "question": question,
        "empty": False,
        "text_value": "",
        "number_value": None,
        "date_value": None,
        "datetime_value": None,
        "boolean_value": None,
        "uploaded_file": None,
        "selected_options": [],
    }

    if question_type in {
        FormQuestion.QuestionType.SHORT_TEXT,
        FormQuestion.QuestionType.LONG_TEXT,
        FormQuestion.QuestionType.EMAIL,
        FormQuestion.QuestionType.PHONE,
    }:
        text_value = str(raw_value).strip()

        if (
            question.minimum_length is not None
            and len(text_value) < question.minimum_length
        ):
            return None, (
                f"Enter at least {question.minimum_length} characters."
            )

        if (
            question.maximum_length is not None
            and len(text_value) > question.maximum_length
        ):
            return None, (
                f"Enter no more than {question.maximum_length} characters."
            )

        if (
            question_type == FormQuestion.QuestionType.EMAIL
            and "@" not in text_value
        ):
            return None, "Enter a valid email address."

        result["text_value"] = text_value

    elif question_type == FormQuestion.QuestionType.NUMBER:
        try:
            number_value = Decimal(str(raw_value))
        except (InvalidOperation, TypeError, ValueError):
            return None, "Enter a valid number."

        if (
            question.minimum_value is not None
            and number_value < question.minimum_value
        ):
            return None, (
                f"The minimum allowed value is "
                f"{question.minimum_value}."
            )

        if (
            question.maximum_value is not None
            and number_value > question.maximum_value
        ):
            return None, (
                f"The maximum allowed value is "
                f"{question.maximum_value}."
            )

        result["number_value"] = number_value

    elif question_type == FormQuestion.QuestionType.DATE:
        date_value = parse_date(str(raw_value))

        if date_value is None:
            return None, "Enter a valid date."

        result["date_value"] = date_value

    elif question_type == FormQuestion.QuestionType.DATETIME:
        datetime_value = parse_datetime(str(raw_value))

        if datetime_value is None:
            return None, "Enter a valid date and time."

        if timezone.is_naive(datetime_value):
            datetime_value = timezone.make_aware(datetime_value)

        result["datetime_value"] = datetime_value

    elif question_type == FormQuestion.QuestionType.YES_NO:
        if raw_value not in {"yes", "no"}:
            return None, "Select Yes or No."

        result["boolean_value"] = raw_value == "yes"

    elif question_type in {
        FormQuestion.QuestionType.SINGLE_CHOICE,
        FormQuestion.QuestionType.DROPDOWN,
    }:
        option = QuestionOption.objects.filter(
            question=question,
            value=raw_value,
            is_active=True,
        ).first()

        if option is None:
            return None, "Select a valid option."

        result["selected_options"] = [option]

    elif question_type == FormQuestion.QuestionType.MULTIPLE_CHOICE:
        options = list(
            QuestionOption.objects.filter(
                question=question,
                value__in=raw_value,
                is_active=True,
            )
        )

        if len(options) != len(set(raw_value)):
            return None, "One or more selected options are invalid."

        result["selected_options"] = options

    elif question_type in {
        FormQuestion.QuestionType.FILE,
        FormQuestion.QuestionType.IMAGE,
    }:
        result["uploaded_file"] = raw_value

    else:
        result["text_value"] = str(raw_value).strip()

    return result, None


@require_http_methods(["GET", "POST"])
def public_event_form(request, event_slug, form_slug):
    event_form = get_public_event_form(
        event_slug=event_slug,
        form_slug=form_slug,
    )

    form_not_open, form_closed = form_availability(event_form)

    sections = (
        event_form.sections
        .filter(is_active=True)
        .prefetch_related(
            "questions__options",
        )
        .order_by("display_order", "id")
    )

    language_code = request.LANGUAGE_CODE
    is_evaluation = event_form.form_type == EventForm.FormType.EVALUATION

    if request.method == "POST":
        if form_not_open:
            return JsonResponse(
                {
                    "success": False,
                    "message": "This form is not open yet.",
                    "errors": {},
                },
                status=400,
            )

        if form_closed:
            return JsonResponse(
                {
                    "success": False,
                    "message": (
                        "The submission period for this form has ended."
                    ),
                    "errors": {},
                },
                status=400,
            )

        if is_evaluation and not event_form.allow_multiple_submissions:
            previous_submission = None
            if request.user.is_authenticated:
                previous_submission = FormSubmission.objects.filter(
                    event_form=event_form,
                    submitted_by=request.user,
                    is_complete=True,
                ).first()
            else:
                previous_reference = request.session.get(
                    "evaluation_submissions",
                    {},
                ).get(str(event_form.pk))
                if previous_reference:
                    previous_submission = FormSubmission.objects.filter(
                        event_form=event_form,
                        reference_number=previous_reference,
                        is_complete=True,
                    ).first()

            if previous_submission:
                return JsonResponse(
                    {
                        "success": False,
                        "duplicate": True,
                        "message": _(
                            "You have already submitted this evaluation."
                        ),
                        "redirect_url": (
                            f"/{language_code}/submissions/"
                            f"{previous_submission.reference_number}/success/"
                        ),
                    },
                    status=409,
                )

        questions = list(
            FormQuestion.objects.filter(
                section__event_form=event_form,
                section__is_active=True,
                is_active=True,
            )
            .select_related("section")
            .prefetch_related("options")
            .order_by(
                "section__display_order",
                "display_order",
                "id",
            )
        )

        errors = {}
        validated_answers = []

        for question in questions:
            answer_data, error = validate_question_answer(
                request,
                question,
            )

            if error:
                errors[str(question.id)] = error
            else:
                validated_answers.append(answer_data)

        if errors:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Please correct the highlighted fields.",
                    "errors": errors,
                },
                status=400,
            )

        submitter_email = ""
        submitter_phone = ""

        for answer_data in validated_answers:
            question = answer_data["question"]

            if (
                question.question_type
                == FormQuestion.QuestionType.EMAIL
                and not submitter_email
            ):
                submitter_email = answer_data.get(
                    "text_value",
                    "",
                )

            if (
                question.question_type
                == FormQuestion.QuestionType.PHONE
                and not submitter_phone
            ):
                submitter_phone = answer_data.get(
                    "text_value",
                    "",
                )

        with transaction.atomic():
            submission = FormSubmission.objects.create(
                event_form=event_form,
                submitted_by=(
                    request.user
                    if request.user.is_authenticated
                    else None
                ),
                language=language_code,
                submitter_email=submitter_email,
                submitter_phone=submitter_phone,
                ip_address=get_client_ip(request),
                user_agent=request.META.get(
                    "HTTP_USER_AGENT",
                    "",
                ),
                is_complete=True,
                created_by=(
                    request.user
                    if request.user.is_authenticated
                    else None
                ),
                updated_by=(
                    request.user
                    if request.user.is_authenticated
                    else None
                ),
            )

            for answer_data in validated_answers:
                if answer_data.get("empty"):
                    continue

                selected_options = answer_data.pop(
                    "selected_options",
                    [],
                )

                question = answer_data.pop("question")
                answer_data.pop("empty", None)

                answer = FormAnswer.objects.create(
                    submission=submission,
                    question=question,
                    **answer_data,
                )

                if selected_options:
                    answer.selected_options.set(
                        selected_options
                    )

        if event_form.form_type != EventForm.FormType.EVALUATION:
            sync_badge_identity_from_answers(submission)
        elif not event_form.allow_multiple_submissions:
            evaluation_submissions = request.session.get(
                "evaluation_submissions",
                {},
            )
            evaluation_submissions[str(event_form.pk)] = (
                submission.reference_number
            )
            request.session["evaluation_submissions"] = (
                evaluation_submissions
            )

        success_url = (
            f"/{language_code}/submissions/"
            f"{submission.reference_number}/success/"
        )

        return JsonResponse(
            {
                "success": True,
                "message": (
                    event_form.success_message_en
                    if language_code == "en"
                    else event_form.success_message_sw
                ),
                "reference_number": submission.reference_number,
                "redirect_url": success_url,
            }
        )

    context = {
        "event_form": event_form,
        "event": event_form.event,
        "sections": sections,
        "language_code": language_code,
        "form_not_open": form_not_open,
        "form_closed": form_closed,
        "is_evaluation": is_evaluation,
    }

    return render(
        request,
        "forms_builder/public_event_form.html",
        context,
    )


def submission_success(request, reference_number):
    submission = get_object_or_404(
        FormSubmission.objects.select_related(
            "event_form",
            "event_form__event",
            "event_form__event__venue",
        ),
        reference_number=reference_number,
        is_complete=True,
    )

    return render(
        request,
        "forms_builder/submission_success.html",
        {
            "submission": submission,
            "event_form": submission.event_form,
            "event": submission.event_form.event,
            "is_evaluation": (
                submission.event_form.form_type
                == EventForm.FormType.EVALUATION
            ),
        },
    )


@require_http_methods(["GET", "POST"])
def registration_status(request):
    submission = None
    lookup_error = ""
    reference_number = request.GET.get("reference", "").strip().upper()

    if request.method == "POST":
        reference_number = (
            request.POST.get("reference_number", "").strip().upper()
        )
        contact = request.POST.get("contact", "").strip()
        candidate = (
            FormSubmission.objects
            .select_related("event_form__event")
            .filter(
                reference_number=reference_number,
                is_complete=True,
                event_form__form_type__in=[
                    EventForm.FormType.REGISTRATION,
                    EventForm.FormType.EXHIBITOR,
                    EventForm.FormType.SPEAKER,
                ],
            )
            .first()
        )

        email_matches = (
            candidate
            and candidate.submitter_email
            and candidate.submitter_email.casefold() == contact.casefold()
        )
        normalized_contact = "".join(contact.split())
        phone_matches = (
            candidate
            and candidate.submitter_phone
            and "".join(candidate.submitter_phone.split())
            == normalized_contact
        )

        if candidate and (email_matches or phone_matches):
            submission = candidate
        else:
            lookup_error = (
                "We could not verify a registration with those details."
            )

    return render(
        request,
        "forms_builder/registration_status.html",
        {
            "submission": submission,
            "lookup_error": lookup_error,
            "reference_number": reference_number,
        },
    )


def get_approved_badge_submission(participant_token):
    return get_object_or_404(
        FormSubmission.objects.select_related(
            "event_form",
            "event_form__event",
            "event_form__event__venue",
        ),
        participant_token=participant_token,
        review_status=FormSubmission.ReviewStatus.APPROVED,
        is_complete=True,
        is_active=True,
        event_form__event__badge_enabled=True,
        event_form__form_type__in=[
            EventForm.FormType.REGISTRATION,
            EventForm.FormType.EXHIBITOR,
            EventForm.FormType.SPEAKER,
        ],
    )


@require_http_methods(["GET"])
def participant_badge(request, participant_token):
    submission = get_approved_badge_submission(participant_token)

    return render(
        request,
        "forms_builder/participant_badge.html",
        {
            "submission": submission,
            "event": submission.event_form.event,
        },
    )


@require_http_methods(["GET"])
def participant_certificate(request, participant_token):
    submission = get_object_or_404(
        FormSubmission.objects.select_related(
            "event_form",
            "event_form__event",
            "event_form__event__venue",
            "check_in",
        ),
        participant_token=participant_token,
        review_status=FormSubmission.ReviewStatus.APPROVED,
        is_complete=True,
        is_active=True,
        event_form__event__certificate_enabled=True,
        check_in__isnull=False,
        event_form__form_type__in=[
            EventForm.FormType.REGISTRATION,
            EventForm.FormType.EXHIBITOR,
            EventForm.FormType.SPEAKER,
        ],
    )

    return render(
        request,
        "forms_builder/participant_certificate.html",
        {
            "submission": submission,
            "event": submission.event_form.event,
            "event_display_name": (
                submission.event_form.event.title_en
                if request.LANGUAGE_CODE == "en"
                else submission.event_form.event.title_sw
            ),
            "certificate_number": certificate_number(submission),
            "event_date_range": event_date_range(
                submission.event_form.event,
                language=request.LANGUAGE_CODE,
            ),
            "verification_url": certificate_verification_url(
                submission,
                request=request,
                language=request.LANGUAGE_CODE,
            ),
        },
    )


def get_certificate_submission(participant_token):
    return get_object_or_404(
        FormSubmission.objects.select_related(
            "event_form",
            "event_form__event",
            "event_form__event__venue",
            "check_in",
        ),
        participant_token=participant_token,
        review_status=FormSubmission.ReviewStatus.APPROVED,
        is_complete=True,
        is_active=True,
        event_form__event__certificate_enabled=True,
        check_in__isnull=False,
        event_form__form_type__in=[
            EventForm.FormType.REGISTRATION,
            EventForm.FormType.EXHIBITOR,
            EventForm.FormType.SPEAKER,
        ],
    )


@require_http_methods(["GET"])
def participant_certificate_qr(request, participant_token):
    submission = get_certificate_submission(participant_token)
    verification_url = certificate_verification_url(
        submission,
        request=request,
        language=submission.language,
    )
    response = HttpResponse(
        generate_qr_png(verification_url),
        content_type="image/png",
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_http_methods(["GET"])
def participant_certificate_pdf(request, participant_token):
    submission = get_certificate_submission(participant_token)
    verification_url = certificate_verification_url(
        submission,
        request=request,
        language=request.LANGUAGE_CODE,
    )
    response = HttpResponse(
        generate_certificate_pdf(
            submission,
            verification_url,
            language=request.LANGUAGE_CODE,
        ),
        content_type="application/pdf",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{submission.reference_number}-certificate.pdf"'
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_http_methods(["GET"])
def certificate_verification(request, participant_token):
    submission = get_certificate_submission(participant_token)
    event = submission.event_form.event
    return render(
        request,
        "forms_builder/certificate_verification.html",
        {
            "submission": submission,
            "event": event,
            "certificate_number": certificate_number(submission),
            "event_date_range": event_date_range(
                event,
                language=request.LANGUAGE_CODE,
            ),
        },
    )


@require_http_methods(["GET"])
def participant_badge_qr(request, participant_token):
    submission = get_approved_badge_submission(participant_token)
    check_in_url = participant_check_in_url(
        submission,
        request=request,
        language=submission.language,
    )
    response = HttpResponse(
        generate_qr_png(check_in_url),
        content_type="image/png",
    )

    if request.GET.get("download") == "1":
        response["Content-Disposition"] = (
            "attachment; "
            f'filename="{submission.reference_number}-badge-qr.png"'
        )

    response["X-Content-Type-Options"] = "nosniff"
    return response
