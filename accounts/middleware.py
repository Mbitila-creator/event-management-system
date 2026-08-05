from django.shortcuts import redirect


class UserPreferredLanguageMiddleware:
    """Keep every authenticated staff workspace in the preferred language."""

    STAFF_PATH_PREFIXES = {"admin", "staff", "check-in", "reports"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user
            and user.is_authenticated
            and request.method == "GET"
            and request.LANGUAGE_CODE != user.preferred_language
        ):
            parts = request.path.split("/")
            is_staff_workspace = (
                len(parts) > 2
                and parts[1] in {"sw", "en"}
                and parts[2] in self.STAFF_PATH_PREFIXES
            )
            if is_staff_workspace:
                parts[1] = user.preferred_language
                target = "/".join(parts)
                query = request.META.get("QUERY_STRING")
                return redirect(f"{target}?{query}" if query else target)
        return self.get_response(request)
