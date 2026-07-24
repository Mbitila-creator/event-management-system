from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import Event, EventCategory


def home(request):
    current_time = timezone.now()

    search_query = request.GET.get("q", "").strip()
    category_slug = request.GET.get("category", "").strip()

    events = (
        Event.objects.select_related(
            "category",
            "venue",
            "venue__council",
            "venue__council__region",
        )
        .filter(
            is_active=True,
            is_public=True,
        )
        .exclude(
            status=Event.Status.CANCELLED,
        )
        .order_by("starts_at")
    )

    if search_query:
        events = events.filter(
            Q(code__icontains=search_query)
            | Q(title_sw__icontains=search_query)
            | Q(title_en__icontains=search_query)
            | Q(description_sw__icontains=search_query)
            | Q(description_en__icontains=search_query)
            | Q(organizer_name__icontains=search_query)
        )

    if category_slug:
        events = events.filter(
            category__slug=category_slug,
        )

    categories = EventCategory.objects.filter(
        is_active=True,
    ).order_by(
        "display_order",
        "name_sw",
    )

    context = {
        "events": events,
        "categories": categories,
        "search_query": search_query,
        "selected_category": category_slug,
        "current_time": current_time,
    }

    return render(
        request,
        "events/home.html",
        context,
    )


def event_detail(request, event_slug):
    event = get_object_or_404(
        Event.objects.select_related(
            "category",
            "venue",
            "venue__council",
            "venue__council__region",
        ).prefetch_related(
            "forms",
        ),
        slug=event_slug,
        is_active=True,
        is_public=True,
    )

    current_time = timezone.now()

    active_forms = event.forms.filter(
        is_active=True,
        is_published=True,
    ).order_by(
        "form_type",
        "name_sw",
    )

    registration_form = active_forms.filter(
        form_type="REGISTRATION",
    ).first()

    if registration_form is None:
        registration_form = active_forms.filter(
            form_type="EXHIBITOR",
        ).first()

    evaluation_form = active_forms.filter(
        form_type="EVALUATION",
    ).first()

    registration_not_open = (
        event.registration_opens_at
        and current_time < event.registration_opens_at
    )

    registration_closed = (
        event.registration_closes_at
        and current_time > event.registration_closes_at
    )

    registration_available = (
        event.registration_enabled
        and event.status
        in [
            Event.Status.PUBLISHED,
            Event.Status.REGISTRATION_OPEN,
        ]
        and not registration_not_open
        and not registration_closed
        and registration_form is not None
    )

    context = {
        "event": event,
        "active_forms": active_forms,
        "registration_form": registration_form,
        "evaluation_form": evaluation_form,
        "registration_not_open": registration_not_open,
        "registration_closed": registration_closed,
        "registration_available": registration_available,
        "current_time": current_time,
    }

    return render(
        request,
        "events/event_detail.html",
        context,
    )