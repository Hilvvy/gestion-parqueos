from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from .models import Reservation


@require_safe
@never_cache
def public_confirmation(request, code):
    reservation = Reservation.objects.filter(code=code).select_related("parking_lot").first()
    context = {"found": bool(reservation)}
    if reservation:
        now = timezone.now()
        status = reservation.status
        deadline = reservation.entry_deadline or reservation.ends_at
        if status == Reservation.Status.CONFIRMED and (
            now > deadline or now >= reservation.ends_at
        ):
            status = Reservation.Status.EXPIRED
        # Lista explícita de datos públicos: nunca se entrega el objeto de reserva al template.
        context.update(
            code=str(reservation.code),
            parking_lot=reservation.parking_lot.name,
            starts_at=reservation.starts_at,
            ends_at=reservation.ends_at,
            deadline=deadline,
            masked_plate="***" + reservation.plate[-3:] if len(reservation.plate) > 3 else "***",
            status_label=Reservation.Status(status).label,
            pending=status == Reservation.Status.CONFIRMED,
        )
    response = render(
        request, "parking/public_confirmation.html", context, status=200 if reservation else 404
    )
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
    )
    return response
