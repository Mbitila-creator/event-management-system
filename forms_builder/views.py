from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import EventForm


def public_event_form(request, event_slug, form_slug):
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

    current_time = timezone.now()

    form_not_open = (
        event_form.opens_at
        and current_time < event_form.opens_at
    )

    form_closed = (
        event_form.closes_at
        and current_time > event_form.closes_at
    )

    sections = (
        event_form.sections
        .filter(is_active=True)
        .prefetch_related(
            "questions__options",
        )
        .order_by("display_order", "id")
    )

    language_code = request.LANGUAGE_CODE

    context = {
        "event_form": event_form,
        "event": event_form.event,
        "sections": sections,
        "language_code": language_code,
        "form_not_open": form_not_open,
        "form_closed": form_closed,
    }

    return render(
        request,
        "forms_builder/public_event_form.html",
        context,
    )
