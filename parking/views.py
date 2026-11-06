from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.db import OperationalError
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ReservationForm
from .models import ClassSchedule, ParkingLot, Reservation
from .services import ReservationService


def availability_rows():
    lots = ParkingLot.objects.annotate(
        occupied=Count("reservation", filter=Q(reservation__status=Reservation.Status.INSIDE))
    )
    return [
        {
            "name": lot.name,
            "capacity": lot.capacity,
            "occupied": lot.occupied,
            "free": max(0, lot.capacity - lot.occupied),
        }
        for lot in lots
    ]


@login_required
def dashboard(request):
    return render(
        request,
        "parking/dashboard.html",
        {
            "lots": availability_rows(),
            "reservations": Reservation.objects.filter(user=request.user).select_related(
                "parking_lot"
            )[:30],
            "schedules": ClassSchedule.objects.filter(
                user=request.user, ends_at__gt=timezone.now()
            ),
        },
    )


@login_required
def reserve(request):
    form = ReservationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            ReservationService.reserve(user=request.user, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        except OperationalError:
            form.add_error(None, "El sistema está ocupado. Intenta nuevamente.")
        else:
            messages.success(request, "Reserva confirmada. Presenta tu placa al ingresar.")
            return redirect("dashboard")
    return render(request, "parking/reserve.html", {"form": form})


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


@user_passes_test(lambda user: user.is_active and user.is_staff)
def access_console(request):
    reservations = Reservation.objects.filter(
        status__in=ReservationService.active_statuses
    ).select_related("user", "parking_lot")
    plate = request.GET.get("plate", "").strip().upper()
    if plate:
        reservations = reservations.filter(plate__icontains=plate)
    return render(
        request, "parking/access.html", {"reservations": reservations[:50], "plate": plate}
    )


@user_passes_test(lambda user: user.is_active and user.is_staff)
@require_POST
def movement(request, pk, action):
    get_object_or_404(Reservation, pk=pk)
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
            messages.success(request, "Movimiento registrado correctamente.")
    return redirect("access")


@login_required
def availability(request):
    return JsonResponse(
        {"lots": availability_rows(), "updated_at": timezone.localtime().strftime("%H:%M:%S")}
    )
