from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import resolve

from .models import UserProfile


class RequirePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and UserProfile.objects.filter(
                user_id=request.user.pk, must_change_password=True
            ).exists()
        ):
            match = resolve(request.path_info)
            # La página local y el worker son públicos; sus API siguen bloqueadas.
            if match.url_name not in (
                "password_change",
                "logout",
                "public_confirmation",
                "offline_shell",
                "service_worker",
            ):
                if (
                    match.url_name in ("offline_context", "sync_movement")
                    or request.content_type == "application/json"
                ):
                    return JsonResponse(
                        {
                            "error": "Cambia tu contraseña temporal antes de continuar.",
                            "password_change_url": "/clave/",
                        },
                        status=403,
                    )
                return redirect("password_change")
        return self.get_response(request)
