from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_existing_reservations_keep_history_and_receive_unique_codes():
    executor = MigrationExecutor(connection)
    target = [("parking", "0002_parkingpolicy_alter_reservation_options_and_more")]
    try:
        executor.migrate([("parking", "0001_initial")])
        old = executor.loader.project_state([("parking", "0001_initial")]).apps
        user = old.get_model("auth", "User").objects.create(username="legacy")
        lot = old.get_model("parking", "ParkingLot").objects.create(name="Legacy", capacity=5)
        start = timezone.now() + timedelta(days=1)
        for plate in ("ABC123", "DEF456"):
            old.get_model("parking", "Reservation").objects.create(
                user=user,
                parking_lot=lot,
                plate=plate,
                starts_at=start,
                ends_at=start + timedelta(hours=2),
            )
        executor = MigrationExecutor(connection)
        executor.migrate(target)
        current = executor.loader.project_state(target).apps
        rows = list(current.get_model("parking", "Reservation").objects.all())
        assert len(rows) == 2
        assert len({row.code for row in rows}) == 2
        assert {row.plate for row in rows} == {"ABC123", "DEF456"}
        assert all(row.entry_deadline == start + timedelta(minutes=15) for row in rows)
        assert all(row.vehicle_id is None for row in rows)
    finally:
        MigrationExecutor(connection).migrate(target)
