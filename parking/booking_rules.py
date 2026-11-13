from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

MAX_ADVANCE = timedelta(hours=48)


def validate_booking_window(starts_at, ends_at):
    now = timezone.now()
    if starts_at >= ends_at:
        raise ValidationError("La hora final debe ser posterior a la inicial.")
    if starts_at <= now:
        raise ValidationError("La reserva debe iniciar en el futuro.")
    if starts_at > now + MAX_ADVANCE:
        raise ValidationError("Solo puedes reservar con un máximo de 48 horas de anticipación.")
