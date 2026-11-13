from django.db.models import Count, Q

from .models import ParkingLot, Reservation
from .permissions import permitted_lots


def availability_rows():
    lots = ParkingLot.objects.annotate(
        occupied=Count("reservation", filter=Q(reservation__status=Reservation.Status.INSIDE))
    )
    return [
        {
            "id": lot.pk,
            "name": lot.name,
            "capacity": lot.capacity,
            "occupied": lot.occupied,
            "free": max(0, lot.capacity - lot.occupied),
        }
        for lot in lots
    ]


def visible_reservations(user):
    reservations = Reservation.objects.select_related(
        "user", "parking_lot", "vehicle", "officer", "exit_officer"
    )
    if user.has_perm("parking.view_operational_report"):
        return reservations
    return reservations.filter(Q(user=user) | Q(parking_lot__in=permitted_lots(user)))


def filter_report(reservations, data):
    if data.get("plate"):
        reservations = reservations.filter(plate__icontains=data["plate"].strip().upper())
    if data.get("date_from"):
        reservations = reservations.filter(starts_at__date__gte=data["date_from"])
    if data.get("date_to"):
        reservations = reservations.filter(starts_at__date__lte=data["date_to"])
    if data.get("status"):
        reservations = reservations.filter(status=data["status"])
    return reservations
