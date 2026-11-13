from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from .booking_rules import validate_booking_window
from .capacity import peak_occupancy
from .models import AuditEvent, ClassSchedule, ParkingLot, ParkingPolicy, Reservation, Vehicle
from .permissions import permitted_lots
from .validators import normalize_plate


class VehicleService:
    @staticmethod
    def register(*, owner, **data):
        vehicle = Vehicle(owner=owner, **data)
        try:
            with transaction.atomic():
                vehicle.full_clean()
                vehicle.save()
                AuditEvent.objects.create(
                    actor=owner, vehicle=vehicle, action=AuditEvent.Action.VEHICLE_ADDED
                )
        except IntegrityError as error:
            raise ValidationError("La placa ya tiene un vehículo activo registrado.") from error
        return vehicle

    @staticmethod
    @transaction.atomic
    def retire(*, vehicle_id, owner):
        vehicle = (
            Vehicle.objects.select_for_update()
            .filter(pk=vehicle_id, owner=owner, active=True)
            .first()
        )
        if not vehicle:
            raise ValidationError("El vehículo no está disponible.")
        if (
            Reservation.objects.filter(vehicle=vehicle)
            .filter(
                Q(status=Reservation.Status.INSIDE)
                | Q(status=Reservation.Status.CONFIRMED, ends_at__gt=timezone.now())
            )
            .exists()
        ):
            raise ValidationError(
                "Cancela las reservas pendientes o registra la salida antes de retirar el vehículo."
            )
        vehicle.active = False
        vehicle.save(update_fields=["active"])
        AuditEvent.objects.create(
            actor=owner, vehicle=vehicle, action=AuditEvent.Action.VEHICLE_RETIRED
        )


class ReservationService:
    """Reglas y transiciones de reserva, ejecutadas en transacciones breves."""

    active_statuses = [Reservation.Status.CONFIRMED, Reservation.Status.INSIDE]
    normalize_plate = staticmethod(normalize_plate)

    @classmethod
    @transaction.atomic
    def expire_no_shows(cls):
        now = timezone.now()
        candidates = (
            Reservation.objects.select_for_update()
            .filter(status=Reservation.Status.CONFIRMED)
            .filter(Q(entry_deadline__lt=now) | Q(ends_at__lte=now))
        )
        count = 0
        for reservation in candidates:
            changed = Reservation.objects.filter(
                pk=reservation.pk, status=Reservation.Status.CONFIRMED
            ).update(status=Reservation.Status.EXPIRED, expired_at=now)
            if changed:
                AuditEvent.objects.create(reservation=reservation, action=AuditEvent.Action.EXPIRED)
                count += 1
        return count

    @classmethod
    @transaction.atomic
    def reserve(
        cls, *, user, parking_lot, vehicle, starts_at, ends_at, purpose=Reservation.Purpose.CLASS
    ):
        cls.expire_no_shows()
        if purpose not in Reservation.Purpose.values:
            raise ValidationError("Motivo de reserva inválido.")
        validate_booking_window(starts_at, ends_at)
        if not ClassSchedule.objects.filter(
            user=user, active=True, starts_at__lte=starts_at, ends_at__gte=ends_at
        ).exists():
            raise ValidationError("La reserva debe estar dentro de uno de tus horarios de clases.")
        # SQLite usa BEGIN IMMEDIATE; la fila del parqueo también protege la asignación.
        if parking_lot is None:
            from .queries import interval_recommendations

            options = interval_recommendations(starts_at, ends_at)
            if not options or options[0]["free"] < 1:
                raise ValidationError("No hay espacios disponibles para esa franja.")
            parking_lot = ParkingLot.objects.get(pk=options[0]["id"])
        ParkingLot.objects.filter(pk=parking_lot.pk).update(revision=F("revision") + 1)
        parking_lot = ParkingLot.objects.select_for_update().get(pk=parking_lot.pk)
        if not parking_lot.active:
            raise ValidationError("El parqueo no está disponible.")
        vehicle = Vehicle.objects.filter(pk=vehicle.pk, owner=user, active=True).first()
        if not vehicle:
            raise ValidationError("Selecciona uno de tus vehículos activos.")
        overlapping = Reservation.objects.filter(
            status__in=cls.active_statuses, starts_at__lt=ends_at, ends_at__gt=starts_at
        )
        if overlapping.filter(plate=vehicle.plate).exists():
            raise ValidationError("Este vehículo ya tiene una reserva en ese horario.")
        intervals = overlapping.filter(parking_lot=parking_lot).values_list("starts_at", "ends_at")
        if peak_occupancy(intervals, starts_at, ends_at) >= parking_lot.capacity:
            raise ValidationError("El parqueo no tiene espacios para esa franja.")
        policy, _ = ParkingPolicy.objects.get_or_create(pk=1)
        deadline = min(ends_at, starts_at + timedelta(minutes=policy.arrival_tolerance_minutes))
        reservation = Reservation.objects.create(
            user=user,
            parking_lot=parking_lot,
            vehicle=vehicle,
            plate=vehicle.plate,
            purpose=purpose,
            starts_at=starts_at,
            ends_at=ends_at,
            entry_deadline=deadline,
        )
        AuditEvent.objects.create(
            actor=user, reservation=reservation, action=AuditEvent.Action.RESERVED
        )
        return reservation

    @staticmethod
    @transaction.atomic
    def cancel(*, reservation_id, user):
        updated = Reservation.objects.filter(
            pk=reservation_id,
            user=user,
            status=Reservation.Status.CONFIRMED,
            starts_at__gt=timezone.now(),
        ).update(status=Reservation.Status.CANCELLED, cancelled_at=timezone.now())
        if not updated:
            raise ValidationError("Solo puedes cancelar tus reservas confirmadas antes del inicio.")
        AuditEvent.objects.create(
            actor=user, reservation_id=reservation_id, action=AuditEvent.Action.CANCELLED
        )

    @classmethod
    def check_in(cls, *, reservation_id, officer):
        if not permitted_lots(officer).exists():
            raise ValidationError(
                "Solo el personal de seguridad asignado puede registrar ingresos."
            )
        cls.expire_no_shows()
        with transaction.atomic():
            reservation = (
                Reservation.objects.select_for_update()
                .select_related("parking_lot")
                .get(pk=reservation_id)
            )
            if not permitted_lots(officer).filter(pk=reservation.parking_lot_id).exists():
                raise ValidationError("No tienes asignado este parqueo.")
            now = timezone.now()
            deadline = reservation.entry_deadline or reservation.ends_at
            if (
                reservation.status != Reservation.Status.CONFIRMED
                or not reservation.starts_at <= now <= deadline
                or now >= reservation.ends_at
            ):
                raise ValidationError(
                    "El ingreso requiere una cita confirmada dentro de su horario y tolerancia."
                )
            ParkingLot.objects.filter(pk=reservation.parking_lot_id).update(
                revision=F("revision") + 1
            )
            inside = Reservation.objects.filter(
                parking_lot_id=reservation.parking_lot_id, status=Reservation.Status.INSIDE
            ).count()
            if inside >= reservation.parking_lot.capacity:
                raise ValidationError("El parqueo está físicamente lleno.")
            if Reservation.objects.filter(
                plate=reservation.plate, status=Reservation.Status.INSIDE
            ).exists():
                raise ValidationError("Este vehículo ya está dentro de un parqueo.")
            reservation.status = Reservation.Status.INSIDE
            reservation.entered_at = now
            reservation.officer = officer
            reservation.save(update_fields=["status", "entered_at", "officer"])
            AuditEvent.objects.create(
                actor=officer, reservation=reservation, action=AuditEvent.Action.ENTERED
            )

    @staticmethod
    @transaction.atomic
    def check_out(*, reservation_id, officer):
        if not permitted_lots(officer).exists():
            raise ValidationError("Solo el personal de seguridad asignado puede registrar salidas.")
        reservation = Reservation.objects.select_for_update().get(pk=reservation_id)
        if not permitted_lots(officer).filter(pk=reservation.parking_lot_id).exists():
            raise ValidationError("No tienes asignado este parqueo.")
        if reservation.status != Reservation.Status.INSIDE:
            raise ValidationError("Solo se puede registrar la salida de un vehículo en parqueo.")
        reservation.status = Reservation.Status.COMPLETED
        reservation.exited_at = timezone.now()
        reservation.exit_officer = officer
        reservation.save(update_fields=["status", "exited_at", "exit_officer"])
        AuditEvent.objects.create(
            actor=officer, reservation=reservation, action=AuditEvent.Action.EXITED
        )
