from django.shortcuts import redirect


class UserPreferredLanguageMiddleware:
    """Apply a staff member's preference once, then permit manual switching."""

    STAFF_PATH_PREFIXES = {"admin", "staff", "check-in", "reports"}
    SESSION_KEY = "preferred_language_applied_user_id"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated and request.method == "GET":
            parts = request.path.split("/")
            is_staff_workspace = (
                len(parts) > 2
                and parts[1] in {"sw", "en"}
                and parts[2] in self.STAFF_PATH_PREFIXES
            )
            preference_not_applied = (
                request.session.get(self.SESSION_KEY) != user.pk
            )
            if is_staff_workspace and preference_not_applied:
                request.session[self.SESSION_KEY] = user.pk
                if request.LANGUAGE_CODE == user.preferred_language:
                    return self.get_response(request)
                parts[1] = user.preferred_language
                target = "/".join(parts)
                query = request.META.get("QUERY_STRING")
                return redirect(f"{target}?{query}" if query else target)
        return self.get_response(request)
