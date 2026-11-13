from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

from parking.models import ClassSchedule, ParkingLot, SecurityAssignment, Vehicle
from parking.permissions import SECURITY_GROUP
from parking.services import VehicleService


@pytest.fixture
def scenario(db):
    user = get_user_model().objects.create_user("student")
    officer = get_user_model().objects.create_user("officer")
    group, _ = Group.objects.get_or_create(name=SECURITY_GROUP)
    officer.groups.add(group)
    lot = ParkingLot.objects.create(name="Norte", capacity=1)
    SecurityAssignment.objects.create(officer=officer, parking_lot=lot)
    start = (timezone.now() + timedelta(days=1)).replace(second=0, microsecond=0)
    end = start + timedelta(hours=2)
    ClassSchedule.objects.create(user=user, course="Calidad", starts_at=start, ends_at=end)
    vehicle = VehicleService.register(
        owner=user, plate="ABC123", kind=Vehicle.Kind.CAR, brand="Toyota"
    )
    return dict(
        user=user,
        officer=officer,
        parking_lot=lot,
        plate="abc123",
        vehicle=vehicle,
        starts_at=start,
        ends_at=end,
    )
