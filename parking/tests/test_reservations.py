from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from parking.models import ParkingLot, Reservation, Vehicle
from parking.services import ReservationService, VehicleService


def reserve(scenario, **overrides):
    plate = overrides.pop("plate", scenario["plate"])
    normalized = ReservationService.normalize_plate(plate)
    vehicle = Vehicle.objects.filter(owner=scenario["user"], plate=normalized, active=True).first()
    if vehicle is None:
        vehicle = VehicleService.register(
            owner=scenario["user"], plate=plate, kind=Vehicle.Kind.CAR, brand="Test"
        )
    data = {key: scenario[key] for key in ("user", "parking_lot", "starts_at", "ends_at")}
    return ReservationService.reserve(**(data | {"vehicle": vehicle} | overrides))


def test_reservation_normalizes_plate(scenario):
    result = reserve(scenario, plate=" abc123 ")
    assert result.plate == "ABC123"
    assert result.status == Reservation.Status.CONFIRMED


@pytest.mark.parametrize("plate", ["x", "ABC 123", "<script>"])
def test_invalid_plate(scenario, plate):
    with pytest.raises(ValidationError):
        reserve(scenario, plate=plate)


def test_rejects_outside_class_schedule(scenario):
    with pytest.raises(ValidationError, match="horarios"):
        reserve(scenario, ends_at=scenario["ends_at"] + timedelta(minutes=1))


def test_rejects_past(scenario):
    with pytest.raises(ValidationError, match="futuro"):
        reserve(scenario, starts_at=timezone.now() - timedelta(minutes=1))


def test_rejects_reversed_interval(scenario):
    with pytest.raises(ValidationError, match="posterior"):
        reserve(scenario, ends_at=scenario["starts_at"])


def test_rejects_full_lot(scenario):
    reserve(scenario)
    with pytest.raises(ValidationError, match="espacios"):
        reserve(scenario, plate="XYZ789")
    assert Reservation.objects.count() == 1


def test_rejects_overlapping_vehicle_across_lots(scenario):
    reserve(scenario)
    other = ParkingLot.objects.create(name="Sur", capacity=5)
    with pytest.raises(ValidationError, match="vehículo"):
        reserve(scenario, parking_lot=other)


def test_adjacent_reservations_do_not_overlap(scenario):
    middle = scenario["starts_at"] + timedelta(hours=1)
    reserve(scenario, ends_at=middle)
    assert reserve(scenario, starts_at=middle).pk


def test_capacity_counts_simultaneous_intervals(scenario):
    lot = scenario["parking_lot"]
    lot.capacity = 2
    lot.save()
    middle = scenario["starts_at"] + timedelta(hours=1)
    reserve(scenario, ends_at=middle)
    reserve(scenario, starts_at=middle, plate="XYZ789")
    assert reserve(scenario, plate="DEF456").pk


def test_cancel_releases_capacity(scenario):
    reservation = reserve(scenario)
    ReservationService.cancel(reservation_id=reservation.pk, user=scenario["user"])
    assert reserve(scenario, plate="XYZ789").pk


def test_other_user_cannot_cancel(scenario):
    reservation = reserve(scenario)
    with pytest.raises(ValidationError):
        ReservationService.cancel(reservation_id=reservation.pk, user=scenario["officer"])
    reservation.refresh_from_db()
    assert reservation.status == Reservation.Status.CONFIRMED


def test_cannot_cancel_after_start(scenario):
    reservation = reserve(scenario)
    with patch("parking.services.timezone.now", return_value=scenario["starts_at"]):
        with pytest.raises(ValidationError):
            ReservationService.cancel(reservation_id=reservation.pk, user=scenario["user"])


def test_entry_and_exit_record_audit(scenario):
    reservation = reserve(scenario)
    with patch("parking.services.timezone.now", return_value=scenario["starts_at"]):
        ReservationService.check_in(reservation_id=reservation.pk, officer=scenario["officer"])
        reservation.refresh_from_db()
        assert reservation.status == Reservation.Status.INSIDE
        assert reservation.entered_at == scenario["starts_at"]
        assert reservation.officer == scenario["officer"]
        with pytest.raises(ValidationError):
            ReservationService.check_in(reservation_id=reservation.pk, officer=scenario["officer"])
        ReservationService.check_out(reservation_id=reservation.pk, officer=scenario["officer"])
    reservation.refresh_from_db()
    assert reservation.status == Reservation.Status.COMPLETED
    assert reservation.exited_at is not None
    with pytest.raises(ValidationError):
        ReservationService.check_out(reservation_id=reservation.pk, officer=scenario["officer"])


@pytest.mark.parametrize("action", ["check_in", "check_out"])
def test_student_cannot_register_movements(scenario, action):
    reservation = reserve(scenario)
    with pytest.raises(ValidationError, match="personal"):
        getattr(ReservationService, action)(reservation_id=reservation.pk, officer=scenario["user"])


def test_entry_outside_window(scenario):
    reservation = reserve(scenario)
    with pytest.raises(ValidationError, match="horario"):
        ReservationService.check_in(reservation_id=reservation.pk, officer=scenario["officer"])


def test_overstaying_vehicle_blocks_entry(scenario):
    reservation = reserve(scenario)
    Reservation.objects.create(
        user=scenario["user"],
        parking_lot=scenario["parking_lot"],
        plate="OLD123",
        starts_at=scenario["starts_at"] - timedelta(hours=3),
        ends_at=scenario["starts_at"] - timedelta(hours=1),
        status=Reservation.Status.INSIDE,
    )
    with patch("parking.services.timezone.now", return_value=scenario["starts_at"]):
        with pytest.raises(ValidationError, match="físicamente"):
            ReservationService.check_in(reservation_id=reservation.pk, officer=scenario["officer"])


def test_anonymous_requires_login(client):
    assert client.get("/").status_code == 302
    assert client.get("/disponibilidad/").status_code == 302


def test_student_dashboard_and_permissions(client, scenario):
    client.force_login(scenario["user"])
    response = client.get("/")
    assert response.status_code == 200
    assert "Disponibilidad actual" in response.content.decode()
    assert client.get("/reservar/").status_code == 200
    assert client.get("/acceso/").status_code == 302
    assert client.get("/disponibilidad/").json()["lots"][0]["free"] == 1


def test_booking_through_form(client, scenario):
    client.force_login(scenario["user"])
    response = client.post(
        "/reservar/",
        {
            "parking_lot": scenario["parking_lot"].pk,
            "vehicle": scenario["vehicle"].pk,
            "starts_at": timezone.localtime(scenario["starts_at"]).strftime("%Y-%m-%dT%H:%M"),
            "ends_at": timezone.localtime(scenario["ends_at"]).strftime("%Y-%m-%dT%H:%M"),
        },
    )
    assert response.status_code == 302
    assert Reservation.objects.get().plate == "ABC123"


def test_console_and_http_methods(client, scenario):
    reservation = reserve(scenario)
    client.force_login(scenario["officer"])
    assert client.get("/acceso/?plate=ABC").status_code == 200
    assert client.get(f"/acceso/{reservation.pk}/entry/").status_code == 405
    client.force_login(scenario["user"])
    assert client.get(f"/reservas/{reservation.pk}/cancelar/").status_code == 405


def test_csrf_required(scenario):
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    client.force_login(scenario["user"])
    assert client.post("/reservar/", {}).status_code == 403


def test_http_entry_updates_availability_and_exit_releases_it(client, scenario):
    reservation = reserve(scenario)
    client.force_login(scenario["officer"])
    with patch("parking.services.timezone.now", return_value=scenario["starts_at"]):
        response = client.post(f"/acceso/{reservation.pk}/entry/")
    assert response.status_code == 302
    assert client.get("/disponibilidad/").json()["lots"][0]["free"] == 0
    assert client.post(f"/acceso/{reservation.pk}/exit/").status_code == 302
    assert client.get("/disponibilidad/").json()["lots"][0]["free"] == 1


def test_other_users_reservation_is_hidden(client, scenario):
    reservation = reserve(scenario)
    client.force_login(scenario["officer"])
    assert b"ABC123" not in client.get("/").content
    assert client.post(f"/reservas/{reservation.pk}/cancelar/").status_code == 404
