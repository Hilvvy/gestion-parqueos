from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from parking.models import AuditEvent, ParkingLot, ParkingPolicy, Reservation, Vehicle
from parking.services import ReservationService, VehicleService
from parking.tests.test_reservations import reserve


def test_vehicle_owner_is_required(scenario):
    other = VehicleService.register(
        owner=scenario["officer"], plate="XYZ789", kind=Vehicle.Kind.CAR, brand="Honda"
    )
    with pytest.raises(ValidationError, match="vehículos activos"):
        ReservationService.reserve(
            user=scenario["user"],
            parking_lot=scenario["parking_lot"],
            vehicle=other,
            starts_at=scenario["starts_at"],
            ends_at=scenario["ends_at"],
        )


def test_other_vehicle_is_rejected_by_form(client, scenario):
    outsider = get_user_model().objects.create_user("other")
    other = VehicleService.register(
        owner=outsider, plate="XYZ789", kind=Vehicle.Kind.CAR, brand="Honda"
    )
    client.force_login(scenario["user"])
    response = client.post(
        reverse("reserve"),
        {
            "vehicle": other.pk,
            "parking_lot": scenario["parking_lot"].pk,
            "starts_at": "2030-01-01T10:00",
            "ends_at": "2030-01-01T11:00",
        },
    )
    assert response.status_code == 200
    assert not Reservation.objects.exists()
    assert "vehicle" in response.context["form"].errors


def test_duplicate_active_plate_rejected(scenario):
    with pytest.raises(ValidationError):
        VehicleService.register(
            owner=scenario["officer"], plate=" abc123 ", kind=Vehicle.Kind.CAR, brand="Honda"
        )


def test_can_replace_retired_vehicle_and_keep_history(scenario):
    vehicle = scenario["vehicle"]
    VehicleService.retire(vehicle_id=vehicle.pk, owner=scenario["user"])
    replacement = VehicleService.register(
        owner=scenario["user"], plate=vehicle.plate, kind=Vehicle.Kind.CAR, brand="Honda"
    )
    vehicle.refresh_from_db()
    assert replacement.pk != vehicle.pk
    assert not vehicle.active
    assert Vehicle.objects.filter(plate=vehicle.plate, active=True).count() == 1


def test_retire_blocked_by_future_reservation(scenario):
    reserve(scenario)
    with pytest.raises(ValidationError, match="reservas pendientes"):
        VehicleService.retire(vehicle_id=scenario["vehicle"].pk, owner=scenario["user"])


def test_cancel_allows_retirement_and_preserves_plate(scenario):
    reservation = reserve(scenario)
    ReservationService.cancel(reservation_id=reservation.pk, user=scenario["user"])
    VehicleService.retire(vehicle_id=scenario["vehicle"].pk, owner=scenario["user"])
    reservation.refresh_from_db()
    assert reservation.plate == "ABC123"
    assert reservation.vehicle_id == scenario["vehicle"].pk
    assert reservation.cancelled_at


def test_retired_vehicle_cannot_reserve(scenario):
    VehicleService.retire(vehicle_id=scenario["vehicle"].pk, owner=scenario["user"])
    with pytest.raises(ValidationError, match="vehículos activos"):
        ReservationService.reserve(
            user=scenario["user"],
            parking_lot=scenario["parking_lot"],
            vehicle=scenario["vehicle"],
            starts_at=scenario["starts_at"],
            ends_at=scenario["ends_at"],
        )


def test_retire_other_users_vehicle_is_hidden(client, scenario):
    client.force_login(scenario["officer"])
    assert client.post(reverse("retire_vehicle", args=[scenario["vehicle"].pk])).status_code == 404


def test_detail_and_local_qr_are_private(client, scenario):
    reservation = reserve(scenario)
    detail = reverse("reservation_detail", args=[reservation.code])
    qr = reverse("reservation_qr", args=[reservation.code])
    assert client.get(qr).status_code == 302
    client.force_login(scenario["user"])
    response = client.get(detail)
    assert response.status_code == 200
    assert "qrserver.com" not in response.content.decode()
    assert str(reservation.code) in response.content.decode()
    response = client.get(qr)
    assert response.status_code == 200
    assert response["Content-Type"] == "image/svg+xml"
    assert b"<svg" in response.content
    assert "no-store" in response["Cache-Control"]
    outsider = get_user_model().objects.create_user("outsider")
    client.force_login(outsider)
    assert client.get(detail).status_code == 404
    assert client.get(qr).status_code == 404


def test_cancel_invalidates_qr_and_code_entry(client, scenario):
    reservation = reserve(scenario)
    ReservationService.cancel(reservation_id=reservation.pk, user=scenario["user"])
    client.force_login(scenario["user"])
    assert client.get(reverse("reservation_qr", args=[reservation.code])).status_code == 410
    with patch("parking.services.timezone.now", return_value=scenario["starts_at"]):
        with pytest.raises(ValidationError):
            ReservationService.check_in(reservation_id=reservation.pk, officer=scenario["officer"])


def test_qr_ends_at_reservation_end_and_detail_avoids_broken_image(client, scenario):
    reservation = reserve(scenario, ends_at=scenario["starts_at"] + timedelta(minutes=5))
    client.force_login(scenario["user"])
    with patch("parking.views.timezone.now", return_value=reservation.ends_at):
        assert client.get(reverse("reservation_qr", args=[reservation.code])).status_code == 410
        assert not client.get(reverse("reservation_detail", args=[reservation.code])).context[
            "qr_available"
        ]


def test_staff_flag_does_not_grant_security_access(client, scenario):
    staff = get_user_model().objects.create_user("staff", is_staff=True)
    client.force_login(staff)
    assert client.get(reverse("access")).status_code == 302
    reservation = reserve(scenario)
    with pytest.raises(ValidationError, match="personal"):
        ReservationService.check_in(reservation_id=reservation.pk, officer=staff)


def test_officer_cannot_view_or_operate_another_lot(client, scenario):
    other = ParkingLot.objects.create(name="Otro", capacity=10)
    reservation = reserve(scenario, parking_lot=other)
    client.force_login(scenario["officer"])
    response = client.get(reverse("access"))
    assert not response.context["reservations"]
    assert client.get(reverse("reservation_detail", args=[reservation.code])).status_code == 404
    assert client.post(reverse("movement", args=[reservation.pk, "entry"])).status_code == 404
    with patch("parking.services.timezone.now", return_value=scenario["starts_at"]):
        with pytest.raises(ValidationError, match="asignado"):
            ReservationService.check_in(reservation_id=reservation.pk, officer=scenario["officer"])


def test_officer_searches_full_code(client, scenario):
    reservation = reserve(scenario)
    client.force_login(scenario["officer"])
    response = client.get(reverse("access"), {"search": str(reservation.code)})
    assert [r.pk for r in response.context["reservations"]] == [reservation.pk]
    assert not client.get(reverse("access"), {"search": "unrelated"}).context["reservations"]


def test_tolerance_is_snapshot_from_policy(scenario):
    ParkingPolicy.objects.create(arrival_tolerance_minutes=5)
    reservation = reserve(scenario)
    assert reservation.entry_deadline == scenario["starts_at"] + timedelta(minutes=5)
    ParkingPolicy.objects.filter(pk=1).update(arrival_tolerance_minutes=30)
    reservation.refresh_from_db()
    assert reservation.entry_deadline == scenario["starts_at"] + timedelta(minutes=5)


def test_expiry_boundary_and_idempotent_audit(scenario):
    reservation = reserve(scenario)
    with patch("parking.services.timezone.now", return_value=reservation.entry_deadline):
        assert ReservationService.expire_no_shows() == 0
    with patch(
        "parking.services.timezone.now",
        return_value=reservation.entry_deadline + timedelta(seconds=1),
    ):
        assert ReservationService.expire_no_shows() == 1
        assert ReservationService.expire_no_shows() == 0
    reservation.refresh_from_db()
    assert reservation.status == Reservation.Status.EXPIRED
    assert reservation.expired_at
    assert (
        AuditEvent.objects.filter(reservation=reservation, action=AuditEvent.Action.EXPIRED).count()
        == 1
    )


def test_entry_at_deadline_allowed_and_inside_not_expired(scenario):
    reservation = reserve(scenario)
    with patch("parking.services.timezone.now", return_value=reservation.entry_deadline):
        ReservationService.check_in(reservation_id=reservation.pk, officer=scenario["officer"])
    with patch(
        "parking.services.timezone.now", return_value=reservation.ends_at + timedelta(hours=1)
    ):
        assert ReservationService.expire_no_shows() == 0
    reservation.refresh_from_db()
    assert reservation.status == Reservation.Status.INSIDE


def test_direct_post_after_tolerance_rejected_and_recorded(client, scenario):
    reservation = reserve(scenario)
    client.force_login(scenario["officer"])
    with patch(
        "parking.services.timezone.now",
        return_value=reservation.entry_deadline + timedelta(seconds=1),
    ):
        response = client.post(reverse("movement", args=[reservation.pk, "entry"]))
    assert response.status_code == 302
    reservation.refresh_from_db()
    assert reservation.status == Reservation.Status.EXPIRED
    assert reservation.entered_at is None
    assert (
        AuditEvent.objects.filter(reservation=reservation, action=AuditEvent.Action.EXPIRED).count()
        == 1
    )


def test_expiry_command_without_web_requests(client, scenario):
    reservation = reserve(scenario)
    with patch(
        "parking.services.timezone.now",
        return_value=reservation.entry_deadline + timedelta(seconds=1),
    ):
        output = StringIO()
        call_command("process_no_shows", stdout=output)
    reservation.refresh_from_db()
    assert reservation.status == Reservation.Status.EXPIRED
    assert "Citas vencidas: 1" in output.getvalue()
    client.force_login(scenario["user"])
    assert client.get(reverse("reservation_qr", args=[reservation.code])).status_code == 410


def test_audit_records_full_lifecycle_and_exit_officer(scenario):
    reservation = reserve(scenario)
    with patch("parking.services.timezone.now", return_value=scenario["starts_at"]):
        ReservationService.check_in(reservation_id=reservation.pk, officer=scenario["officer"])
        ReservationService.check_out(reservation_id=reservation.pk, officer=scenario["officer"])
    reservation.refresh_from_db()
    assert reservation.exit_officer == scenario["officer"]
    assert list(
        AuditEvent.objects.filter(reservation=reservation)
        .order_by("pk")
        .values_list("action", flat=True)
    ) == ["reserved", "entered", "exited"]


@pytest.mark.parametrize("page", ["reports", "report_csv", "audit"])
def test_reports_require_explicit_permission(client, scenario, page):
    client.force_login(scenario["officer"])
    assert client.get(reverse(page)).status_code == 403
    client.force_login(scenario["user"])
    assert client.get(reverse(page)).status_code == 403


def allow_reports(user):
    user.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="parking", codename="view_operational_report"
        )
    )


def test_report_and_csv_share_plate_and_date_filters(client, scenario):
    first = reserve(scenario)
    # Otra fecha y placa para comprobar que el CSV no exporte todo el historial.
    Reservation.objects.create(
        user=scenario["user"],
        parking_lot=scenario["parking_lot"],
        plate="XYZ789",
        starts_at=scenario["starts_at"] + timedelta(days=2),
        ends_at=scenario["ends_at"] + timedelta(days=2),
    )
    allow_reports(scenario["officer"])
    client.force_login(scenario["officer"])
    dates = {
        "plate": "abc",
        "date_from": timezone.localtime(first.starts_at).date().isoformat(),
        "date_to": timezone.localtime(first.ends_at).date().isoformat(),
    }
    response = client.get(reverse("reports"), dates)
    assert response.context["total"] == 1
    assert [r.pk for r in response.context["reservations"]] == [first.pk]
    csv = client.get(reverse("report_csv"), dates)
    assert csv.status_code == 200
    assert b"ABC123" in csv.content and b"XYZ789" not in csv.content
    assert "no-store" in csv["Cache-Control"]


def test_invalid_report_dates_show_no_rows_and_no_csv(client, scenario):
    reserve(scenario)
    allow_reports(scenario["officer"])
    client.force_login(scenario["officer"])
    params = {"date_from": "2030-02-02", "date_to": "2030-01-01"}
    assert client.get(reverse("reports"), params).context["total"] == 0
    assert client.get(reverse("report_csv"), params).status_code == 400


def test_csv_neutralizes_spreadsheet_formula(client, scenario):
    scenario["user"].username = "=1+1"
    scenario["user"].save()
    reserve(scenario)
    allow_reports(scenario["officer"])
    client.force_login(scenario["officer"])
    csv = client.get(reverse("report_csv")).content.decode("utf-8-sig")
    assert "'=1+1" in csv


def test_profile_cannot_change_role(client, scenario):
    client.force_login(scenario["user"])
    response = client.post(
        reverse("profile"),
        {
            "first_name": "Andrea",
            "last_name": "Gómez",
            "email": "demo@ulacit.ed.cr",
            "is_superuser": "true",
            "is_staff": "true",
        },
    )
    assert response.status_code == 302
    scenario["user"].refresh_from_db()
    assert scenario["user"].first_name == "Andrea"
    assert not scenario["user"].is_superuser and not scenario["user"].is_staff
    assert AuditEvent.objects.filter(
        actor=scenario["user"], action=AuditEvent.Action.PROFILE_UPDATED
    ).exists()


def test_seed_is_idempotent_and_assigns_explicit_roles(db):
    call_command("seed_demo", password="DemoTest2026!", stdout=StringIO())
    student = get_user_model().objects.get(username="estudiante")
    before = student.password
    call_command("seed_demo", password="OtherPassword2026!", stdout=StringIO())
    student.refresh_from_db()
    assert student.password == before
    assert Vehicle.objects.filter(owner=student, active=True).count() == 1
    assert get_user_model().objects.get(username="oficial").groups.filter(name="Seguridad").exists()
    assert (
        Group.objects.get(name="Administración")
        .permissions.filter(codename="view_operational_report")
        .exists()
    )
