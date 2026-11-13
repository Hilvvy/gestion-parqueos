"""Proceso aislado para probar bloqueos reales sobre un archivo SQLite."""

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.core.exceptions import ValidationError  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import connections  # noqa: E402
from django.utils import timezone  # noqa: E402

from parking.models import (  # noqa: E402
    AuditEvent,
    ClassSchedule,
    ParkingLot,
    Reservation,  # noqa: E402
    Vehicle,
)
from parking.services import ReservationService  # noqa: E402

call_command("migrate", verbosity=0)
lot = ParkingLot.objects.create(name="Último espacio", capacity=1)
start = timezone.now() + timedelta(days=1)
end = start + timedelta(hours=2)
people = []
for index in range(2):
    user = get_user_model().objects.create_user(f"student{index}")
    vehicle = Vehicle.objects.create(
        owner=user, plate=f"ABC{index}", kind=Vehicle.Kind.CAR, brand="Test"
    )
    ClassSchedule.objects.create(user=user, course="Calidad", starts_at=start, ends_at=end)
    people.append((user, vehicle))

barrier = threading.Barrier(2)


def book(person):
    user, vehicle = person
    try:
        barrier.wait(timeout=10)
        ReservationService.reserve(
            user=user,
            vehicle=vehicle,
            parking_lot=None if os.getenv("AUTO_ASSIGN") == "1" else lot,
            starts_at=start,
            ends_at=end,
        )
        return "confirmed"
    except ValidationError as error:
        assert "espacios" in str(error)
        return "rejected"
    finally:
        connections.close_all()


with ThreadPoolExecutor(max_workers=2) as executor:
    outcomes = sorted(executor.map(book, people))
assert outcomes == ["confirmed", "rejected"], outcomes
assert Reservation.objects.count() == 1
assert AuditEvent.objects.filter(action=AuditEvent.Action.RESERVED).count() == 1
print(json.dumps({"outcomes": outcomes, "confirmed_count": Reservation.objects.count()}))
connections.close_all()
