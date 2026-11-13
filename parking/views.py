import csv
import io
from uuid import UUID

import segno
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.core.exceptions import ValidationError
from django.db import OperationalError, transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .forms import ProfileForm, ReportFilterForm, ReservationForm, VehicleForm
from .models import AuditEvent, ClassSchedule, Reservation, Vehicle
from .permissions import is_security, permitted_lots
from .queries import availability_rows, filter_report, visible_reservations
from .services import ReservationService, VehicleService


@login_required
def dashboard(request):
    reservations = Reservation.objects.filter(user=request.user).select_related("parking_lot")
    return render(
        request,
        "parking/dashboard.html",
        {
            "lots": availability_rows(),
            "reservations": reservations[:30],
            "next_reservation": reservations.filter(
                status=Reservation.Status.CONFIRMED, ends_at__gt=timezone.now()
            )
            .order_by("starts_at")
            .first(),
            "schedules": ClassSchedule.objects.filter(
                user=request.user, ends_at__gt=timezone.now()
            ),
        },
    )


@login_required
def reserve(request):
    form = ReservationForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            reservation = ReservationService.reserve(user=request.user, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        except OperationalError:
            form.add_error(None, "El sistema está ocupado. Intenta nuevamente.")
        else:
            messages.success(request, "Reserva confirmada.")
            return redirect("reservation_detail", code=reservation.code)
    return render(
        request,
        "parking/reserve.html",
        {"form": form, "has_vehicles": form.fields["vehicle"].queryset.exists()},
    )


@login_required
@require_POST
def cancel(request, pk):
    get_object_or_404(Reservation, pk=pk, user=request.user)
    try:
        ReservationService.cancel(reservation_id=pk, user=request.user)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, "Reserva cancelada.")
    return redirect("dashboard")


@login_required
@never_cache
def reservation_detail(request, code):
    reservation = get_object_or_404(visible_reservations(request.user), code=code)
    now = timezone.now()
    qr_available = (
        reservation.status == Reservation.Status.CONFIRMED
        and now <= (reservation.entry_deadline or reservation.ends_at)
        and now < reservation.ends_at
    )
    return render(
        request, "parking/detail.html", {"reservation": reservation, "qr_available": qr_available}
    )


@login_required
@never_cache
def reservation_qr(request, code):
    reservation = get_object_or_404(visible_reservations(request.user), code=code)
    deadline = reservation.entry_deadline or reservation.ends_at
    now = timezone.now()
    if (
        reservation.status != Reservation.Status.CONFIRMED
        or now > deadline
        or now >= reservation.ends_at
    ):
        return HttpResponse("Código no disponible.", status=410, content_type="text/plain")
    output = io.BytesIO()
    segno.make(str(reservation.code), micro=False).save(output, kind="svg", scale=5)
    return HttpResponse(output.getvalue(), content_type="image/svg+xml")


@user_passes_test(is_security)
def access_console(request):
    reservations = Reservation.objects.filter(
        parking_lot__in=permitted_lots(request.user), status__in=ReservationService.active_statuses
    ).select_related("user", "parking_lot")
    query = request.GET.get("search", request.GET.get("plate", "")).strip()
    if query:
        match = Q(plate__icontains=query.upper())
        try:
            match |= Q(code=UUID(query))
        except ValueError:
            pass
        reservations = reservations.filter(match)
    return render(
        request,
        "parking/access.html",
        {
            "reservations": reservations[:50],
            "search": query,
            "assignments": permitted_lots(request.user),
        },
    )


@user_passes_test(is_security)
@require_POST
def movement(request, pk, action):
    get_object_or_404(Reservation, pk=pk, parking_lot__in=permitted_lots(request.user))
    handlers = {"entry": ReservationService.check_in, "exit": ReservationService.check_out}
    if action not in handlers:
        messages.error(request, "Acción inválida.")
    else:
        try:
            handlers[action](reservation_id=pk, officer=request.user)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        except OperationalError:
            messages.error(request, "El sistema está ocupado. Intenta nuevamente.")
        else:
            messages.success(request, "Movimiento registrado.")
    return redirect("access")


@login_required
def availability(request):
    return JsonResponse(
        {"lots": availability_rows(), "updated_at": timezone.localtime().strftime("%H:%M:%S")}
    )


@login_required
def vehicles(request):
    form = VehicleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            VehicleService.register(owner=request.user, **form.cleaned_data)
        except ValidationError as error:
            for message in error.messages:
                form.add_error(None, message)
        else:
            messages.success(request, "Vehículo registrado.")
            return redirect("vehicles")
    return render(
        request,
        "parking/vehicles.html",
        {"form": form, "vehicles": Vehicle.objects.filter(owner=request.user, active=True)},
    )


@login_required
@require_POST
def retire_vehicle(request, pk):
    get_object_or_404(Vehicle, pk=pk, owner=request.user)
    try:
        VehicleService.retire(vehicle_id=pk, owner=request.user)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, "Vehículo retirado.")
    return redirect("vehicles")


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
            AuditEvent.objects.create(actor=request.user, action=AuditEvent.Action.PROFILE_UPDATED)
        messages.success(request, "Perfil actualizado.")
        return redirect("profile")
    return render(request, "parking/profile.html", {"form": form})


def report_data(request):
    form = ReportFilterForm(request.GET)
    rows = Reservation.objects.select_related("user", "parking_lot", "officer", "exit_officer")
    if form.is_valid():
        rows = filter_report(rows, form.cleaned_data)
    else:
        rows = rows.none()
    return form, rows


@permission_required("parking.view_operational_report", raise_exception=True)
@never_cache
def reports(request):
    form, rows = report_data(request)
    return render(
        request,
        "parking/reports.html",
        {
            "form": form,
            "reservations": rows[:200],
            "total": rows.count(),
            "query": request.GET.urlencode(),
        },
    )


def csv_cell(value):
    value = str(value or "")
    # Evita interpretar datos de usuario como fórmulas al abrir el CSV.
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r", "\n") else value


@permission_required("parking.view_operational_report", raise_exception=True)
def report_csv(request):
    form, rows = report_data(request)
    if not form.is_valid():
        return HttpResponse("Filtros inválidos.", status=400, content_type="text/plain")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="reservas.csv"'
    response["Cache-Control"] = "private, no-store"
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(
        [
            "Placa",
            "Usuario",
            "Parqueo",
            "Inicio",
            "Fin",
            "Estado",
            "Ingreso",
            "Oficial ingreso",
            "Salida",
            "Oficial salida",
        ]
    )

    def date_text(value):
        return timezone.localtime(value).isoformat(timespec="minutes") if value else ""

    for row in rows.iterator():
        writer.writerow(
            [
                csv_cell(row.plate),
                csv_cell(row.user.username),
                csv_cell(row.parking_lot.name),
                date_text(row.starts_at),
                date_text(row.ends_at),
                row.get_status_display(),
                date_text(row.entered_at),
                csv_cell(row.officer.username if row.officer else ""),
                date_text(row.exited_at),
                csv_cell(row.exit_officer.username if row.exit_officer else ""),
            ]
        )
    return response


@permission_required("parking.view_auditevent", raise_exception=True)
@never_cache
def audit_log(request):
    events = AuditEvent.objects.select_related("actor", "reservation", "vehicle")[:100]
    return render(request, "parking/audit.html", {"events": events})
