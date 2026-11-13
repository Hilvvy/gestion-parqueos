from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import OfflineMovement, Reservation
from .permissions import is_security, permitted_lots
from .services import ReservationService


class MovementConflict(ValidationError):
    pass


class OfflineMovementService:
    @staticmethod
    @transaction.atomic
    def synchronize(*, officer, event_id, code, action, occurred_at):
        if not is_security(officer):
            raise ValidationError("Solo Seguridad puede sincronizar movimientos.")
        if action not in ("entry", "exit") or timezone.is_naive(occurred_at):
            raise ValidationError("Movimiento inválido.")
        previous = OfflineMovement.objects.filter(pk=event_id).select_related("reservation").first()
        if previous:
            if (
                previous.officer_id != officer.pk
                or previous.reservation.code != code
                or previous.action != action
                or previous.occurred_at != occurred_at
            ):
                raise MovementConflict("El identificador pertenece a otro movimiento.")
            return previous
        reservation = Reservation.objects.get(code=code, parking_lot__in=permitted_lots(officer))
        now = timezone.now()
        event = OfflineMovement(
            id=event_id,
            officer=officer,
            reservation=reservation,
            action=action,
            occurred_at=occurred_at,
        )
        try:
            if not now - timedelta(hours=24) <= occurred_at <= now + timedelta(seconds=60):
                raise ValidationError(
                    "El registro debe sincronizarse dentro de 24 horas. Revisa el reloj del dispositivo."
                )
            # Un rechazo revierte la transición, pero conserva el resultado del UUID.
            with transaction.atomic():
                handler = (
                    ReservationService.check_in
                    if action == "entry"
                    else ReservationService.check_out
                )
                handler(reservation_id=reservation.pk, officer=officer, occurred_at=occurred_at)
        except ValidationError as error:
            event.error = error.messages[0][:250]
        else:
            event.accepted = True
        event.save(force_insert=True)
        return event
