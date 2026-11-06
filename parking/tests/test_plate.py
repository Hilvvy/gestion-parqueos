import pytest
from django.core.exceptions import ValidationError

from parking.services import ReservationService


def test_plate_normalization_without_database():
    assert ReservationService.normalize_plate("  ab-123  ") == "AB-123"


@pytest.mark.parametrize("plate", ["", "AB", "ABC 123", "A" * 13])
def test_plate_validation_without_database(plate):
    with pytest.raises(ValidationError):
        ReservationService.normalize_plate(plate)
