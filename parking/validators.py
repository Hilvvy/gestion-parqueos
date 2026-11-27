import re
from urllib.parse import urlsplit
from uuid import UUID

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

INSTITUTIONAL_DOMAIN = "ulacit.ed.cr"


def reservation_code(value):
    """Acepta el UUID original o la dirección de confirmación del QR, sin abrir enlaces."""
    value = value.strip()
    try:
        return UUID(value)
    except ValueError:
        url = urlsplit(value)
        parts = url.path.strip("/").split("/")
        if url.scheme not in ("", "http", "https") or len(parts) != 2 or parts[0] != "confirmacion":
            raise ValueError("Código de reserva inválido.") from None
        return UUID(parts[1])


def institutional_email(value):
    value = value.strip().lower()
    validate_email(value)
    if value.rsplit("@", 1)[-1] != INSTITUTIONAL_DOMAIN:
        raise ValidationError("Utiliza tu correo institucional @ulacit.ed.cr.")
    return value


def normalize_plate(plate):
    plate = plate.strip().upper()
    if not re.fullmatch(r"[A-Z0-9-]{3,12}", plate):
        raise ValidationError("La placa debe tener entre 3 y 12 letras, números o guiones.")
    return plate
