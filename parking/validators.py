import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

INSTITUTIONAL_DOMAIN = "ulacit.ed.cr"


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
