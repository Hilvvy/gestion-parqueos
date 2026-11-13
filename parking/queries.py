from datetime import timedelta

from django.db.models import Count, Q
from django.db.models.functions import ExtractHour
from django.utils import timezone

from .capacity import peak_occupancy
from .models import ParkingLot, Reservation
from .permissions import permitted_lots


def availability_rows():
    lots = ParkingLot.objects.filter(active=True).annotate(
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


def interval_recommendations(starts_at, ends_at):
    now = timezone.now()
    reservations = Reservation.objects.filter(starts_at__lt=ends_at, ends_at__gt=starts_at).filter(
        Q(status=Reservation.Status.INSIDE)
        | (
            Q(status=Reservation.Status.CONFIRMED)
            & (Q(entry_deadline__gte=now) | Q(entry_deadline__isnull=True))
        )
    )
    intervals = {}
    for lot_id, start, end in reservations.values_list("parking_lot_id", "starts_at", "ends_at"):
        intervals.setdefault(lot_id, []).append((start, end))
    result = []
    for lot in ParkingLot.objects.filter(active=True):
        used = peak_occupancy(intervals.get(lot.pk, []), starts_at, ends_at)
        result.append(
            {
                "id": lot.pk,
                "name": lot.name,
                "capacity": lot.capacity,
                "free": max(0, lot.capacity - used),
            }
        )
    return sorted(result, key=lambda lot: (-lot["free"], lot["name"]))


def operational_alerts(user):
    now = timezone.now()
    rows = Reservation.objects.filter(
        parking_lot__in=permitted_lots(user), status=Reservation.Status.CONFIRMED
    )
    upcoming = rows.filter(starts_at__gt=now, starts_at__lte=now + timedelta(minutes=30)).order_by(
        "starts_at"
    )
    pending = rows.filter(starts_at__lte=now, ends_at__gt=now, entry_deadline__gte=now).order_by(
        "entry_deadline"
    )
    return {
        "upcoming": upcoming.select_related("parking_lot")[:10],
        "upcoming_count": upcoming.count(),
        "pending": pending.select_related("parking_lot")[:10],
        "pending_count": pending.count(),
        "updated_at": timezone.localtime(now).strftime("%H:%M:%S"),
    }


def monthly_summary(month):
    rows = Reservation.objects.filter(
        starts_at__date__gte=month,
        starts_at__date__lt=(month.replace(day=28) + timedelta(days=4)).replace(day=1),
    )
    top = (
        rows.values("parking_lot__name")
        .annotate(count=Count("pk"))
        .order_by("-count", "parking_lot__name")
        .first()
    )
    peak = (
        rows.annotate(hour=ExtractHour("starts_at", tzinfo=timezone.get_current_timezone()))
        .values("hour")
        .annotate(count=Count("pk"))
        .order_by("-count", "hour")
        .first()
    )
    states = dict(rows.values("status").annotate(count=Count("pk")).values_list("status", "count"))
    return {
        "total": rows.count(),
        "cancelled": states.get(Reservation.Status.CANCELLED, 0),
        "top_lot": top["parking_lot__name"] if top else "—",
        "peak_hour": f"{peak['hour']:02}:00" if peak else "—",
        "states": [
            {"name": label, "count": states.get(value, 0)}
            for value, label in Reservation.Status.choices
        ],
    }
