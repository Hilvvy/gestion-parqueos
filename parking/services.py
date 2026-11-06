import re

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import ClassSchedule, ParkingLot, Reservation


class ReservationService:
    """Centraliza las reglas y transiciones del ciclo de una reserva."""

    active_statuses = [Reservation.Status.CONFIRMED, Reservation.Status.INSIDE]

    @staticmethod
    def normalize_plate(plate):
        plate = plate.strip().upper()
        if not re.fullmatch(r"[A-Z0-9-]{3,12}", plate):
            raise ValidationError("La placa debe tener entre 3 y 12 letras, números o guiones.")
        return plate

    @classmethod
    @transaction.atomic
    def reserve(cls, *, user, parking_lot, plate, starts_at, ends_at):
        plate = cls.normalize_plate(plate)
        if starts_at >= ends_at:
            raise ValidationError("La hora final debe ser posterior a la inicial.")
        if starts_at <= timezone.now():
            raise ValidationError("La reserva debe iniciar en el futuro.")
        if not ClassSchedule.objects.filter(
            user=user, starts_at__lte=starts_at, ends_at__gte=ends_at
        ).exists():
            raise ValidationError("La reserva debe estar dentro de uno de tus horarios de clases.")
        # Una escritura previa serializa reservas en SQLite antes de consultar cupos.
        ParkingLot.objects.filter(pk=parking_lot.pk).update(revision=F("revision") + 1)
        parking_lot.refresh_from_db()
        overlapping = Reservation.objects.filter(
            status__in=cls.active_statuses,
            starts_at__lt=ends_at,
            ends_at__gt=starts_at,
        )
        if overlapping.filter(plate=plate).exists():
            raise ValidationError("Este vehículo ya tiene una reserva en ese horario.")
        # Barrido de intervalos: cuenta el máximo simultáneo, no todas las reservas.
        events = []
        for start, end in overlapping.filter(parking_lot=parking_lot).values_list(
            "starts_at", "ends_at"
        ):
            events.extend([(max(start, starts_at), 1), (min(end, ends_at), -1)])
        occupied = 0
        for _, change in sorted(events):
            occupied += change
            if occupied >= parking_lot.capacity:
                raise ValidationError("El parqueo no tiene espacios para esa franja.")
        return Reservation.objects.create(
            user=user, parking_lot=parking_lot, plate=plate, starts_at=starts_at, ends_at=ends_at
        )

    @staticmethod
    @transaction.atomic
    def cancel(*, reservation_id, user):
        updated = Reservation.objects.filter(
            pk=reservation_id,
            user=user,
            status=Reservation.Status.CONFIRMED,
            starts_at__gt=timezone.now(),
        ).update(status=Reservation.Status.CANCELLED)
        if not updated:
            raise ValidationError("Solo puedes cancelar tus reservas confirmadas antes del inicio.")

    @staticmethod
    @transaction.atomic
    def check_in(*, reservation_id, officer):
        if not officer.is_staff:
            raise ValidationError("Solo el personal de seguridad puede registrar ingresos.")
        now = timezone.now()
        reservation = Reservation.objects.select_related("parking_lot").get(pk=reservation_id)
        ParkingLot.objects.filter(pk=reservation.parking_lot_id).update(revision=F("revision") + 1)
        inside = Reservation.objects.filter(
            parking_lot_id=reservation.parking_lot_id, status=Reservation.Status.INSIDE
        ).count()
        if inside >= reservation.parking_lot.capacity:
            raise ValidationError("El parqueo está físicamente lleno.")
        updated = Reservation.objects.filter(
            pk=reservation_id,
            status=Reservation.Status.CONFIRMED,
            starts_at__lte=now,
            ends_at__gt=now,
        ).update(status=Reservation.Status.INSIDE, entered_at=now, officer=officer)
        if not updated:
            raise ValidationError("El ingreso requiere una cita confirmada dentro de su horario.")

    @staticmethod
    def check_out(*, reservation_id, officer):
        if not officer.is_staff:
            raise ValidationError("Solo el personal de seguridad puede registrar salidas.")
        updated = Reservation.objects.filter(
            pk=reservation_id, status=Reservation.Status.INSIDE
        ).update(status=Reservation.Status.COMPLETED, exited_at=timezone.now())
        if not updated:
            raise ValidationError("Solo se puede registrar la salida de un vehículo en parqueo.")
