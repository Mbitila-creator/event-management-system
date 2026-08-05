from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from .models import User


@login_required(login_url="accounts:staff_login")
def role_home(request):
    """Send each signed-in user to the interface intended for their role."""
    if request.user.is_superuser or request.user.role in {
        User.Role.SYSTEM_ADMIN,
        User.Role.EVENT_ADMIN,
        User.Role.REGISTRATION_OFFICER,
    }:
        return redirect("admin:index")
    if request.user.role == User.Role.ATTENDANCE_OFFICER:
        return redirect("checkin:lookup")
    if request.user.role == User.Role.REPORT_OFFICER:
        return redirect("checkin:reports")
    return redirect("forms_builder:registration_status")


@require_POST
def staff_logout(request):
    logout(request)
    return redirect("accounts:staff_login")
