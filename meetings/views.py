import calendar
import csv
from collections import defaultdict
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from accounts.models import User
from events.models import Event

from .forms import (
    ActionProgressForm,
    AttendanceOnlyForm,
    AttendeeProgressForm,
    InvitationResponseForm,
    MeetingActionItemForm,
    MeetingAgendaItemForm,
    MeetingAttendeeForm,
    MeetingDecisionForm,
    MeetingMinutesForm,
    MeetingWorkflowForm,
)
from .models import (
    Meeting,
    MeetingActionItem,
    MeetingAttendee,
    MeetingDecision,
)
from .services import send_meeting_invitation


MEETING_VIEW_ROLES = {
    User.Role.SYSTEM_ADMIN,
    User.Role.EVENT_ADMIN,
    User.Role.ATTENDANCE_OFFICER,
    User.Role.REPORT_OFFICER,
    User.Role.DIRECTOR,
    User.Role.ASSISTANT_DIRECTOR,
}
MEETING_MANAGER_ROLES = {
    User.Role.SYSTEM_ADMIN,
    User.Role.EVENT_ADMIN,
}


def _can_manage(user):
    return bool(
        user.is_authenticated
        and user.is_active
        and (user.is_superuser or user.role in MEETING_MANAGER_ROLES)
    )


def _can_record_attendance(user):
    return bool(
        user.is_authenticated
        and user.is_active
        and (
            user.is_superuser
            or user.role in MEETING_MANAGER_ROLES
            or user.role == User.Role.ATTENDANCE_OFFICER
        )
    )


def _require_view_access(user):
    if not (
        user.is_authenticated
        and user.is_active
        and (user.is_superuser or user.role in MEETING_VIEW_ROLES)
    ):
        raise PermissionDenied


def _require_manager(user):
    if not _can_manage(user):
        raise PermissionDenied


def _meeting_queryset():
    return Meeting.objects.select_related(
        "event", "event__category", "event__venue", "minutes_approved_by",
    ).prefetch_related(
        "agenda_items", "attendees__user", "decisions__agenda_item",
        "action_items__decision", "action_items__responsible_user",
    )


def _form_error_message(form):
    first_error = next(
        (
            str(error)
            for errors in form.errors.values()
            for error in errors
        ),
        _("Check the information entered and try again."),
    )
    return first_error


def _month_value(raw_value):
    try:
        return date.fromisoformat(f"{raw_value}-01")
    except (TypeError, ValueError):
        return timezone.localdate().replace(day=1)


def _next_month(month):
    return (month.replace(day=28) + timedelta(days=4)).replace(day=1)


def _report_actions(request):
    actions = MeetingActionItem.objects.select_related(
        "meeting", "meeting__event", "responsible_user",
    ).filter(is_active=True, meeting__is_active=True)
    selected_status = request.GET.get("status", "OPEN").strip().upper()
    selected_meeting = request.GET.get("meeting", "").strip()
    closed_statuses = {
        MeetingActionItem.Status.COMPLETED,
        MeetingActionItem.Status.CANCELLED,
    }
    if selected_status == "OPEN":
        actions = actions.exclude(status__in=closed_statuses)
    elif selected_status == "OVERDUE":
        actions = actions.filter(
            Q(status=MeetingActionItem.Status.OVERDUE)
            | Q(due_date__lt=timezone.localdate()),
        ).exclude(status__in=closed_statuses)
    elif selected_status in MeetingActionItem.Status.values:
        actions = actions.filter(status=selected_status)
    else:
        selected_status = "ALL"
    if selected_meeting.isdigit():
        actions = actions.filter(meeting_id=selected_meeting)
    else:
        selected_meeting = ""
    today = timezone.localdate()
    rows = list(actions.order_by("due_date", "meeting__event__starts_at"))
    for action in rows:
        action.is_report_overdue = bool(
            action.status == MeetingActionItem.Status.OVERDUE
            or (
                action.due_date
                and action.due_date < today
                and action.status not in closed_statuses
            )
        )
    return rows, selected_status, selected_meeting


def _safe_csv_value(value):
    rendered = "" if value is None else str(value)
    if rendered.startswith(("=", "+", "-", "@")):
        return f"'{rendered}"
    return rendered


@login_required(login_url="accounts:staff_login")
def meeting_list(request):
    _require_view_access(request.user)
    meetings = Meeting.objects.select_related(
        "event", "event__venue",
    ).annotate(
        participant_count=Count(
            "attendees",
            filter=Q(attendees__is_active=True),
            distinct=True,
        ),
        action_count=Count(
            "action_items",
            filter=Q(action_items__is_active=True),
            distinct=True,
        ),
    ).order_by("-event__starts_at")
    search_query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    meeting_type = request.GET.get("type", "").strip()
    if search_query:
        meetings = meetings.filter(
            Q(reference_number__icontains=search_query)
            | Q(event__code__icontains=search_query)
            | Q(event__title_sw__icontains=search_query)
            | Q(event__title_en__icontains=search_query)
            | Q(chairperson_name__icontains=search_query)
        )
    if status:
        meetings = meetings.filter(event__status=status)
    if meeting_type:
        meetings = meetings.filter(meeting_type=meeting_type)
    context = {
        "meetings": meetings,
        "search_query": search_query,
        "selected_status": status,
        "selected_type": meeting_type,
        "event_status_choices": Event.Status.choices,
        "meeting_type_choices": Meeting.MeetingType.choices,
        "can_manage": _can_manage(request.user),
        "total_meetings": Meeting.objects.filter(is_active=True).count(),
        "upcoming_meetings": Meeting.objects.filter(
            is_active=True,
            event__starts_at__gte=timezone.now(),
        ).count(),
        "open_actions": MeetingActionItem.objects.filter(
            is_active=True,
        ).exclude(
            status__in={
                MeetingActionItem.Status.COMPLETED,
                MeetingActionItem.Status.CANCELLED,
            },
        ).count(),
    }
    return render(request, "meetings/meeting_list.html", context)


@login_required(login_url="accounts:staff_login")
@require_GET
def meeting_calendar(request):
    _require_view_access(request.user)
    selected_month = _month_value(request.GET.get("month"))
    following_month = _next_month(selected_month)
    meetings = _meeting_queryset().filter(
        is_active=True,
        event__starts_at__date__gte=selected_month,
        event__starts_at__date__lt=following_month,
    ).order_by("event__starts_at")
    meetings_by_date = defaultdict(list)
    for meeting in meetings:
        meetings_by_date[timezone.localdate(meeting.event.starts_at)].append(meeting)
    weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(
        selected_month.year,
        selected_month.month,
    ):
        weeks.append([
            {
                "date": day,
                "in_month": day.month == selected_month.month,
                "meetings": meetings_by_date.get(day, []),
            }
            for day in week
        ])
    previous_month = (selected_month - timedelta(days=1)).replace(day=1)
    return render(request, "meetings/meeting_calendar.html", {
        "weeks": weeks,
        "selected_month": selected_month,
        "previous_month": previous_month,
        "next_month": following_month,
        "meeting_count": len(meetings),
    })


@login_required(login_url="accounts:staff_login")
@require_GET
def action_report(request):
    _require_view_access(request.user)
    actions, selected_status, selected_meeting = _report_actions(request)
    all_actions = MeetingActionItem.objects.filter(
        is_active=True,
        meeting__is_active=True,
    )
    closed_statuses = {
        MeetingActionItem.Status.COMPLETED,
        MeetingActionItem.Status.CANCELLED,
    }
    context = {
        "actions": actions,
        "selected_status": selected_status,
        "selected_meeting": selected_meeting,
        "meetings": Meeting.objects.filter(is_active=True).select_related(
            "event",
        ).order_by("-event__starts_at"),
        "status_choices": MeetingActionItem.Status.choices,
        "summary": {
            "total": all_actions.count(),
            "open": all_actions.exclude(status__in=closed_statuses).count(),
            "completed": all_actions.filter(
                status=MeetingActionItem.Status.COMPLETED,
            ).count(),
            "overdue": all_actions.filter(
                Q(status=MeetingActionItem.Status.OVERDUE)
                | Q(due_date__lt=timezone.localdate()),
            ).exclude(status__in=closed_statuses).count(),
        },
    }
    return render(request, "meetings/action_report.html", context)


@login_required(login_url="accounts:staff_login")
@require_GET
def action_report_csv(request):
    _require_view_access(request.user)
    actions, _selected_status, _selected_meeting = _report_actions(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response.write("\ufeff")
    response["Content-Disposition"] = (
        'attachment; filename="meeting-action-report.csv"'
    )
    writer = csv.writer(response)
    writer.writerow([
        _("Meeting reference"), _("Meeting"), _("Action number"),
        _("Action"), _("Responsible person"), _("Due date"),
        _("Status"), _("Progress notes"),
    ])
    language = request.LANGUAGE_CODE
    for action in actions:
        description = (
            action.description_en
            if language == "en" and action.description_en
            else action.description_sw
        )
        status = _("Overdue") if action.is_report_overdue else action.get_status_display()
        writer.writerow([_safe_csv_value(value) for value in (
            action.meeting.reference_number,
            action.meeting.event.title_en if language == "en" else action.meeting.event.title_sw,
            action.action_number,
            description,
            action.responsible_name,
            action.due_date.isoformat() if action.due_date else "",
            status,
            action.progress_notes,
        )])
    return response


@login_required(login_url="accounts:staff_login")
@require_GET
def meeting_print(request, meeting_id):
    _require_view_access(request.user)
    meeting = get_object_or_404(_meeting_queryset(), pk=meeting_id, is_active=True)
    attendees = meeting.attendees.filter(is_active=True).order_by("full_name")
    present_count = attendees.filter(
        attendance_status=MeetingAttendee.AttendanceStatus.PRESENT,
    ).count()
    return render(request, "meetings/meeting_print.html", {
        "meeting": meeting,
        "agenda_items": meeting.agenda_items.filter(is_active=True),
        "attendees": attendees,
        "decisions": meeting.decisions.filter(is_active=True),
        "action_items": meeting.action_items.filter(is_active=True),
        "present_count": present_count,
        "quorum_met": (
            present_count >= meeting.quorum_required
            if meeting.quorum_required
            else None
        ),
    })


@login_required(login_url="accounts:staff_login")
def meeting_create(request):
    _require_manager(request.user)
    form = MeetingWorkflowForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        meeting = form.save(request.user)
        messages.success(request, _("The meeting was created successfully."))
        return redirect("meetings:meeting_detail", meeting_id=meeting.pk)
    return render(request, "meetings/meeting_form.html", {
        "form": form,
        "page_title": _("Create meeting"),
        "submit_label": _("Create meeting and continue"),
    })


@login_required(login_url="accounts:staff_login")
def meeting_edit(request, meeting_id):
    _require_manager(request.user)
    meeting = get_object_or_404(_meeting_queryset(), pk=meeting_id, is_active=True)
    form = MeetingWorkflowForm(request.POST or None, instance=meeting)
    if request.method == "POST" and form.is_valid():
        meeting = form.save(request.user)
        messages.success(request, _("The meeting details were updated successfully."))
        return redirect("meetings:meeting_detail", meeting_id=meeting.pk)
    return render(request, "meetings/meeting_form.html", {
        "form": form,
        "meeting": meeting,
        "page_title": _("Edit meeting"),
        "submit_label": _("Save meeting changes"),
    })


@login_required(login_url="accounts:staff_login")
def meeting_detail(request, meeting_id):
    _require_view_access(request.user)
    meeting = get_object_or_404(_meeting_queryset(), pk=meeting_id, is_active=True)
    attendees = meeting.attendees.filter(is_active=True).order_by("full_name")
    actions = meeting.action_items.filter(is_active=True).order_by("action_number")
    present_count = attendees.filter(
        attendance_status=MeetingAttendee.AttendanceStatus.PRESENT,
    ).count()
    context = {
        "meeting": meeting,
        "agenda_items": meeting.agenda_items.filter(is_active=True),
        "attendees": attendees,
        "decisions": meeting.decisions.filter(is_active=True),
        "action_items": actions,
        "can_manage": _can_manage(request.user),
        "can_record_attendance": _can_record_attendance(request.user),
        "participant_count": attendees.count(),
        "accepted_count": attendees.filter(
            response_status=MeetingAttendee.ResponseStatus.ACCEPTED,
        ).count(),
        "present_count": present_count,
        "quorum_met": (
            present_count >= meeting.quorum_required
            if meeting.quorum_required
            else None
        ),
        "open_action_count": actions.exclude(
            status__in={
                MeetingActionItem.Status.COMPLETED,
                MeetingActionItem.Status.CANCELLED,
            },
        ).count(),
        "response_choices": MeetingAttendee.ResponseStatus.choices,
        "attendance_choices": MeetingAttendee.AttendanceStatus.choices,
        "action_status_choices": MeetingActionItem.Status.choices,
        "agenda_form": MeetingAgendaItemForm(),
        "attendee_form": MeetingAttendeeForm(),
        "minutes_form": MeetingMinutesForm(instance=meeting),
        "decision_form": MeetingDecisionForm(
            meeting=meeting,
            instance=MeetingDecision(meeting=meeting),
        ),
        "action_form": MeetingActionItemForm(
            meeting=meeting,
            instance=MeetingActionItem(meeting=meeting),
        ),
    }
    return render(request, "meetings/meeting_detail.html", context)


@login_required(login_url="accounts:staff_login")
@require_POST
def agenda_add(request, meeting_id):
    _require_manager(request.user)
    meeting = get_object_or_404(Meeting, pk=meeting_id, is_active=True)
    form = MeetingAgendaItemForm(request.POST)
    if form.is_valid():
        agenda = form.save(commit=False)
        agenda.meeting = meeting
        agenda.created_by = request.user
        agenda.updated_by = request.user
        agenda.save()
        messages.success(request, _("The agenda item was added."))
    else:
        messages.error(request, _form_error_message(form))
    return redirect(f"{meeting.get_absolute_url()}#agenda")


@login_required(login_url="accounts:staff_login")
@require_POST
def attendee_add(request, meeting_id):
    _require_manager(request.user)
    meeting = get_object_or_404(Meeting, pk=meeting_id, is_active=True)
    form = MeetingAttendeeForm(request.POST)
    if form.is_valid():
        attendee = form.save(commit=False)
        attendee.meeting = meeting
        attendee.created_by = request.user
        attendee.updated_by = request.user
        attendee.save()
        messages.success(request, _("The participant was added to the invitation list."))
    else:
        messages.error(request, _form_error_message(form))
    return redirect(f"{meeting.get_absolute_url()}#participants")


@login_required(login_url="accounts:staff_login")
@require_POST
def attendee_update(request, meeting_id, attendee_id):
    if not _can_record_attendance(request.user):
        raise PermissionDenied
    meeting = get_object_or_404(Meeting, pk=meeting_id, is_active=True)
    attendee = get_object_or_404(
        MeetingAttendee,
        pk=attendee_id,
        meeting=meeting,
        is_active=True,
    )
    manager = _can_manage(request.user)
    form_class = AttendeeProgressForm if manager else AttendanceOnlyForm
    form = form_class(request.POST)
    if form.is_valid():
        if manager:
            new_response = form.cleaned_data["response_status"]
            if new_response != attendee.response_status:
                attendee.response_status = new_response
                attendee.responded_at = timezone.now()
        new_attendance = form.cleaned_data["attendance_status"]
        attendee.attendance_status = new_attendance
        attendee.checked_in_at = (
            timezone.now()
            if new_attendance == MeetingAttendee.AttendanceStatus.PRESENT
            else None
        )
        attendee.updated_by = request.user
        attendee.save()
        messages.success(request, _("The participant status was updated."))
    else:
        messages.error(request, _form_error_message(form))
    return redirect(f"{meeting.get_absolute_url()}#participants")


@login_required(login_url="accounts:staff_login")
@require_POST
def invitation_send(request, meeting_id, attendee_id):
    _require_manager(request.user)
    meeting = get_object_or_404(Meeting, pk=meeting_id, is_active=True)
    attendee = get_object_or_404(
        MeetingAttendee,
        pk=attendee_id,
        meeting=meeting,
        is_active=True,
    )
    try:
        delivered = send_meeting_invitation(attendee, request=request)
        if delivered:
            messages.success(request, _("The meeting invitation was sent."))
        else:
            messages.error(request, _("The email service did not confirm delivery."))
    except Exception as error:
        messages.error(
            request,
            _("The invitation could not be sent: %(error)s") % {"error": str(error)},
        )
    return redirect(f"{meeting.get_absolute_url()}#participants")


@login_required(login_url="accounts:staff_login")
@require_POST
def minutes_update(request, meeting_id):
    _require_manager(request.user)
    meeting = get_object_or_404(Meeting, pk=meeting_id, is_active=True)
    form = MeetingMinutesForm(request.POST, request.FILES, instance=meeting)
    if form.is_valid():
        minutes = form.save(commit=False)
        if minutes.minutes_status == Meeting.MinutesStatus.APPROVED:
            minutes.minutes_approved_by = request.user
            minutes.minutes_approved_at = timezone.now()
        else:
            minutes.minutes_approved_by = None
            minutes.minutes_approved_at = None
        minutes.updated_by = request.user
        minutes.save()
        messages.success(request, _("The meeting minutes were updated."))
    else:
        messages.error(request, _form_error_message(form))
    return redirect(f"{meeting.get_absolute_url()}#minutes")


@login_required(login_url="accounts:staff_login")
@require_POST
def decision_add(request, meeting_id):
    _require_manager(request.user)
    meeting = get_object_or_404(Meeting, pk=meeting_id, is_active=True)
    form = MeetingDecisionForm(
        request.POST,
        meeting=meeting,
        instance=MeetingDecision(meeting=meeting),
    )
    if form.is_valid():
        decision = form.save(commit=False)
        decision.meeting = meeting
        decision.created_by = request.user
        decision.updated_by = request.user
        decision.save()
        messages.success(request, _("The meeting decision was recorded."))
    else:
        messages.error(request, _form_error_message(form))
    return redirect(f"{meeting.get_absolute_url()}#decisions")


@login_required(login_url="accounts:staff_login")
@require_POST
def action_add(request, meeting_id):
    _require_manager(request.user)
    meeting = get_object_or_404(Meeting, pk=meeting_id, is_active=True)
    form = MeetingActionItemForm(
        request.POST,
        meeting=meeting,
        instance=MeetingActionItem(meeting=meeting),
    )
    if form.is_valid():
        action = form.save(commit=False)
        action.meeting = meeting
        action.created_by = request.user
        action.updated_by = request.user
        action.save()
        messages.success(request, _("The action item was assigned."))
    else:
        messages.error(request, _form_error_message(form))
    return redirect(f"{meeting.get_absolute_url()}#actions")


@login_required(login_url="accounts:staff_login")
@require_POST
def action_update(request, meeting_id, action_id):
    _require_manager(request.user)
    meeting = get_object_or_404(Meeting, pk=meeting_id, is_active=True)
    action = get_object_or_404(
        MeetingActionItem,
        pk=action_id,
        meeting=meeting,
        is_active=True,
    )
    form = ActionProgressForm(request.POST)
    if form.is_valid():
        action.status = form.cleaned_data["status"]
        action.progress_notes = form.cleaned_data["progress_notes"]
        action.completed_at = (
            timezone.now()
            if action.status == MeetingActionItem.Status.COMPLETED
            else None
        )
        action.updated_by = request.user
        action.save()
        messages.success(request, _("The action progress was updated."))
    else:
        messages.error(request, _form_error_message(form))
    return redirect(f"{meeting.get_absolute_url()}#actions")


def invitation_response(request, response_token):
    attendee = get_object_or_404(
        MeetingAttendee.objects.select_related(
            "meeting__event", "meeting__event__venue",
        ),
        response_token=response_token,
        is_active=True,
        meeting__is_active=True,
    )
    form = InvitationResponseForm(
        request.POST or None,
        initial={"response_status": attendee.response_status},
    )
    submitted = False
    if request.method == "POST" and form.is_valid():
        attendee.response_status = form.cleaned_data["response_status"]
        attendee.responded_at = timezone.now()
        attendee.save(update_fields=[
            "response_status", "responded_at", "updated_at",
        ])
        submitted = True
    return render(request, "meetings/invitation_response.html", {
        "attendee": attendee,
        "meeting": attendee.meeting,
        "form": form,
        "submitted": submitted,
    })
