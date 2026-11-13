import re

from django.core.exceptions import ValidationError


def normalize_plate(plate):
    plate = plate.strip().upper()
    if not re.fullmatch(r"[A-Z0-9-]{3,12}", plate):
        raise ValidationError("La placa debe tener entre 3 y 12 letras, números o guiones.")
    return plate
