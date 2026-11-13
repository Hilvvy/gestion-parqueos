from datetime import timedelta

import pytest
from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from parking.administration import AdministrationService
from parking.models import AuditEvent, ParkingPolicy, Reservation, Vehicle
from parking.services import VehicleService
from parking.tests.test_parity import account_data
from parking.tests.test_parity import manager as manager
from parking.tests.test_reservations import reserve


def test_login_accepts_username_and_unique_email(db):
    user = get_user_model().objects.create_user(
        "student-login", email="person@example.test", password="GoodPassword2026!"
    )
    assert authenticate(username="student-login", password="GoodPassword2026!") == user
    assert authenticate(username="PERSON@EXAMPLE.TEST", password="GoodPassword2026!") == user
    assert authenticate(username="person@example.test", password="wrong") is None
    user.is_active = False
    user.save()
    assert authenticate(username="person@example.test", password="GoodPassword2026!") is None


def test_ambiguous_email_does_not_authenticate(db):
    for username in ("first", "second"):
        get_user_model().objects.create_user(
            username, email="same@example.test", password="GoodPassword2026!"
        )
    assert authenticate(username="same@example.test", password="GoodPassword2026!") is None


def test_custom_user_administration_rejects_duplicate_email(manager):
    AdministrationService.save_account(actor=manager, data=account_data())
    with pytest.raises(ValidationError, match="correo"):
        AdministrationService.save_account(
            actor=manager, data=account_data(username="another", national_id="TEST-OTHER")
        )
    assert not get_user_model().objects.filter(username="another").exists()


def test_vehicle_year_validation(scenario):
    vehicle = VehicleService.register(
        owner=scenario["user"], plate="DEF456", kind=Vehicle.Kind.CAR, brand="Honda", year=2022
    )
    assert vehicle.year == 2022
    with pytest.raises(ValidationError):
        VehicleService.register(
            owner=scenario["user"], plate="BAD123", kind=Vehicle.Kind.CAR, brand="Honda", year=1800
        )


def test_reservation_purpose_preserves_schedule_rule(scenario):
    reservation = reserve(scenario, purpose=Reservation.Purpose.EVENT)
    assert reservation.purpose == Reservation.Purpose.EVENT
    with pytest.raises(ValidationError, match="horarios"):
        reserve(
            scenario,
            plate="DEF456",
            purpose=Reservation.Purpose.APPOINTMENT,
            ends_at=scenario["ends_at"] + timedelta(hours=1),
        )


def test_invalid_reservation_purpose_rejected(scenario):
    with pytest.raises(ValidationError, match="Motivo"):
        reserve(scenario, purpose="invalid")


def test_administration_role_operates_all_lots_without_superuser(client, manager, scenario):
    admin = AdministrationService.save_account(
        actor=manager, data=account_data(role="administrator")
    )
    assert not admin.is_superuser and not admin.is_staff
    client.force_login(admin)
    assert client.get(reverse("access")).status_code == 200
    assert client.get(reverse("manage_accounts")).status_code == 200


def test_custom_policy_screen_updates_only_new_reservations(client, manager, scenario):
    before = reserve(scenario)
    client.force_login(manager)
    response = client.post(reverse("manage_policy"), {"arrival_tolerance_minutes": 5})
    assert response.status_code == 302
    assert ParkingPolicy.objects.get(pk=1).arrival_tolerance_minutes == 5
    before.refresh_from_db()
    assert before.entry_deadline == before.starts_at + timedelta(minutes=15)
    assert AuditEvent.objects.filter(
        action=AuditEvent.Action.POLICY_UPDATED, actor=manager
    ).exists()


@pytest.mark.parametrize(
    "page",
    [
        "manage_account_create",
        "manage_lots",
        "manage_lot_create",
        "manage_policy",
        "indicators",
        "subjects",
    ],
)
def test_new_pages_render_for_administrator(client, manager, page):
    client.force_login(manager)
    response = client.get(reverse(page))
    assert response.status_code == 200
    assert b"<form" in response.content or b"<table" in response.content
