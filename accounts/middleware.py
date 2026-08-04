from django.shortcuts import redirect


class UserPreferredLanguageMiddleware:
    """Keep authenticated staff administration in their chosen language."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user
            and user.is_authenticated
            and request.method == "GET"
            and "/admin/" in request.path
            and request.LANGUAGE_CODE != user.preferred_language
        ):
            parts = request.path.split("/")
            if len(parts) > 1 and parts[1] in {"sw", "en"}:
                parts[1] = user.preferred_language
                target = "/".join(parts)
                query = request.META.get("QUERY_STRING")
                return redirect(f"{target}?{query}" if query else target)
        return self.get_response(request)
