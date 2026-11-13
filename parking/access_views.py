import json
from uuid import UUID

from django.contrib.auth.decorators import permission_required, user_passes_test
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .forms import ExceptionEntryForm, VisitorForm
from .models import Reservation
from .offline import MovementConflict, OfflineMovementService
from .permissions import is_security, permitted_lots
from .services import ReservationService


@permission_required("parking.manage_operations", raise_exception=True)
@never_cache
def visitor(request):
    form = VisitorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            reservation = ReservationService.reserve(
                user=request.user, vehicle=None, **form.cleaned_data
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            return redirect("reservation_detail", code=reservation.code)
    return render(
        request, "parking/special_entry.html", {"form": form, "title": "Cita de visitante"}
    )


@user_passes_test(is_security)
@never_cache
def exception_entry(request):
    form = ExceptionEntryForm(request.POST or None, officer=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            reservation = ReservationService.admit_exception(
                officer=request.user, **form.cleaned_data
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            return redirect("reservation_detail", code=reservation.code)
    return render(
        request, "parking/special_entry.html", {"form": form, "title": "Ingreso excepcional"}
    )


@never_cache
def offline_context(request):
    if not is_security(request.user):
        return JsonResponse({"error": "Inicia sesión como oficial."}, status=403)
    rows = (
        Reservation.objects.filter(
            parking_lot__in=permitted_lots(request.user),
            status__in=ReservationService.active_statuses,
        )
        .select_related("parking_lot")
        .order_by("starts_at")[:500]
    )
    return JsonResponse(
        {
            "user": request.user.pk,
            "email": request.user.email,
            "csrf": get_token(request),
            "updated_at": timezone.now().isoformat(),
            "rows": [
                {
                    "code": str(row.code),
                    "plate": row.plate,
                    "lot": row.parking_lot.name,
                    "status": row.status,
                    "start": row.starts_at.isoformat(),
                    "deadline": (row.entry_deadline or row.ends_at).isoformat(),
                    "end": row.ends_at.isoformat(),
                }
                for row in rows
            ],
        }
    )


@require_POST
@never_cache
def sync_movement(request):
    if not is_security(request.user):
        return JsonResponse({"error": "Inicia sesión como oficial."}, status=403)
    try:
        payload = json.loads(request.body)
        event_id, code = UUID(payload["id"]), UUID(payload["code"])
        action = payload["action"]
        occurred_at = parse_datetime(payload["occurred_at"])
        if action not in ("entry", "exit") or not occurred_at or timezone.is_naive(occurred_at):
            raise ValueError
    except (ValueError, KeyError, TypeError, AttributeError):
        return JsonResponse({"error": "Movimiento inválido."}, status=400)
    try:
        event = OfflineMovementService.synchronize(
            officer=request.user,
            event_id=event_id,
            code=code,
            action=action,
            occurred_at=occurred_at,
        )
    except MovementConflict as error:
        return JsonResponse({"error": error.messages[0]}, status=409)
    except Reservation.DoesNotExist:
        return JsonResponse({"error": "Reserva no disponible para este oficial."}, status=404)
    return JsonResponse({"accepted": event.accepted, "error": event.error})


def offline_shell(request):
    return render(request, "parking/offline.html")


def service_worker(request):
    # Solo se cachean recursos públicos, nunca páginas autenticadas ni respuestas de la API.
    response = HttpResponse(
        render(request, "parking/service-worker.js").content, content_type="application/javascript"
    )
    response["Cache-Control"] = "no-cache"
    return response
