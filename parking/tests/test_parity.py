from datetime import date, datetime, time, timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from parking.administration import AdministrationService, SubjectService
from parking.forms import AccountForm
from parking.models import (
    AuditEvent,
    ClassSchedule,
    ParkingLot,
    Reservation,
    SecurityAssignment,
    Subject,
    UserProfile,
)
from parking.permissions import configure_roles
from parking.queries import interval_recommendations, monthly_summary
from parking.services import ReservationService
from parking.tests.test_reservations import reserve


@pytest.fixture
def manager(db):
    return get_user_model().objects.create_user("manager", is_staff=True, is_superuser=True)


def account_data(**changes):
    return {
        "username": "newperson",
        "first_name": "Andrea",
        "last_name": "Demo",
        "email": "person@ulacit.ed.cr",
        "password": "Q8!sZp4x-2026",
        "role": "student",
        "national_id": "TEST-101",
        "birth_date": date(2000, 1, 1),
        "career": "Informática",
        "shift": "",
        "work_start": None,
        "work_end": None,
        "parking_lots": [],
        **changes,
    }


def subject_data(**changes):
    first = timezone.localdate() + timedelta(days=1)
    return {
        "name": "Calidad semanal",
        "weekday": first.weekday(),
        "start_time": time(10),
        "end_time": time(12),
        "first_date": first,
        "weeks": 3,
        **changes,
    }


def browser_data(data):
    return {key: "" if value is None else value for key, value in data.items()}


@pytest.mark.parametrize(
    "page",
    [
        "manage_accounts",
        "manage_account_create",
        "manage_lots",
        "manage_lot_create",
        "manage_policy",
    ],
)
def test_management_is_not_available_to_students_or_officers(client, scenario, page):
    for user in (scenario["user"], scenario["officer"]):
        client.force_login(user)
        assert client.get(reverse(page)).status_code == 403


def test_create_account_from_custom_screen(client, manager):
    client.force_login(manager)
    data = account_data()
    data["birth_date"] = "2000-01-01"
    response = client.post(
        reverse("manage_account_create"),
        browser_data(data) | {"is_superuser": "true", "is_staff": "true"},
    )
    assert response.status_code == 302
    user = get_user_model().objects.get(username="newperson")
    assert user.check_password(data["password"])
    assert not user.is_superuser and not user.is_staff
    assert user.userprofile.career == "Informática"
    assert AuditEvent.objects.filter(
        subject_user=user, action=AuditEvent.Action.USER_CREATED
    ).exists()


def test_create_officer_with_shift_and_assignments(manager, scenario):
    user = AdministrationService.save_account(
        actor=manager,
        data=account_data(
            role="security",
            parking_lots=[scenario["parking_lot"]],
            shift="night",
            work_start=time(22),
            work_end=time(6),
        ),
    )
    assert user.groups.filter(name="Seguridad").exists()
    assert user.userprofile.shift == "night"
    assert SecurityAssignment.objects.filter(
        officer=user, parking_lot=scenario["parking_lot"]
    ).exists()


def test_officer_form_requires_an_assignment(db):
    form = AccountForm(account_data(role="security"))
    assert not form.is_valid()
    assert "parking_lots" in form.errors


def test_weak_initial_password_is_rejected(client, manager):
    client.force_login(manager)
    response = client.post(
        reverse("manage_account_create"), browser_data(account_data(password="1234"))
    )
    assert response.status_code == 200
    assert not get_user_model().objects.filter(username="newperson").exists()


def test_edit_user_does_not_reset_password(client, manager):
    user = AdministrationService.save_account(actor=manager, data=account_data())
    before = user.password
    client.force_login(manager)
    data = account_data(first_name="Actualizada", password="InjectedPassword1!")
    response = client.post(reverse("manage_account_edit", args=[user.pk]), browser_data(data))
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.first_name == "Actualizada"
    assert user.password == before


def test_duplicate_identity_rolls_back_new_user(manager):
    AdministrationService.save_account(actor=manager, data=account_data())
    with pytest.raises(ValidationError):
        AdministrationService.save_account(
            actor=manager, data=account_data(username="duplicate", email="second@ulacit.ed.cr")
        )
    assert not get_user_model().objects.filter(username="duplicate").exists()


def test_regular_manager_cannot_modify_superuser(client, manager, scenario):
    _, group = configure_roles()
    actor = scenario["user"]
    actor.groups.add(group)
    client.force_login(actor)
    assert client.get(reverse("manage_account_edit", args=[manager.pk])).status_code == 403
    assert client.post(reverse("manage_account_toggle", args=[manager.pk])).status_code == 403
    manager.refresh_from_db()
    assert manager.is_active


def test_admin_cannot_deactivate_self(manager):
    with pytest.raises(ValidationError, match="propia cuenta"):
        AdministrationService.toggle_account(actor=manager, user_id=manager.pk)
    manager.refresh_from_db()
    assert manager.is_active


def test_disabling_account_invalidates_session_and_preserves_history(manager, scenario):
    reservation = reserve(scenario)
    student_client = Client()
    student_client.force_login(scenario["user"])
    AdministrationService.toggle_account(actor=manager, user_id=scenario["user"].pk)
    assert student_client.get(reverse("dashboard")).status_code == 302
    assert Reservation.objects.filter(pk=reservation.pk).exists()
    AdministrationService.toggle_account(actor=manager, user_id=scenario["user"].pk)
    scenario["user"].refresh_from_db()
    assert scenario["user"].is_active


def test_role_change_removes_security_assignments(manager, scenario):
    user = scenario["officer"]
    data = account_data(username=user.username, national_id="", role="student")
    AdministrationService.save_account(actor=manager, user_id=user.pk, data=data)
    assert not SecurityAssignment.objects.filter(officer=user).exists()
    assert not user.groups.filter(name="Seguridad").exists()


def test_account_search_and_pagination_render(client, manager, scenario):
    client.force_login(manager)
    response = client.get(reverse("manage_accounts"), {"q": "student"})
    assert response.status_code == 200
    assert [user.username for user in response.context["page"]] == ["student"]


def test_extended_profile_and_identity_lock(client, scenario):
    client.force_login(scenario["user"])
    data = {
        "first_name": "Andrea",
        "last_name": "Gómez",
        "email": "demo@ulacit.ed.cr",
        "details-national_id": "TEST-STUDENT",
        "details-birth_date": "2001-01-01",
        "details-career": "Informática",
    }
    assert client.post(reverse("profile"), data).status_code == 302
    assert (
        client.post(reverse("profile"), data | {"details-national_id": "FORGED"}).status_code == 302
    )
    profile = UserProfile.objects.get(user=scenario["user"])
    assert profile.national_id == "TEST-STUDENT"
    assert profile.birth_date == date(2001, 1, 1)


def test_future_birthdate_rejected_without_partial_profile_save(client, scenario):
    client.force_login(scenario["user"])
    response = client.post(
        reverse("profile"),
        {"first_name": "Invalid", "last_name": "", "email": "", "details-birth_date": "2999-01-01"},
    )
    assert response.status_code == 200
    scenario["user"].refresh_from_db()
    assert scenario["user"].first_name == ""


def test_subject_generates_weekly_classes_and_allows_booking(scenario):
    subject = SubjectService.register(
        actor=scenario["user"], user=scenario["user"], data=subject_data()
    )
    classes = list(ClassSchedule.objects.filter(subject=subject))
    assert len(classes) == 3
    assert all(timezone.localtime(row.starts_at).weekday() == subject.weekday for row in classes)
    assert classes[1].starts_at - classes[0].starts_at == timedelta(days=7)
    first = classes[0]
    reservation = ReservationService.reserve(
        user=scenario["user"],
        vehicle=scenario["vehicle"],
        parking_lot=scenario["parking_lot"],
        starts_at=first.starts_at,
        ends_at=first.ends_at,
    )
    assert reservation.pk


def test_self_reported_subject_is_owned_by_current_user(client, scenario):
    client.force_login(scenario["user"])
    data = subject_data()
    data["first_date"] = data["first_date"].isoformat()
    response = client.post(reverse("subjects"), data | {"user": scenario["officer"].pk})
    assert response.status_code == 302
    subject = Subject.objects.get()
    assert subject.user == scenario["user"] and subject.registered_by == scenario["user"]


def test_duplicate_subject_does_not_duplicate_classes(scenario):
    data = subject_data()
    subject = SubjectService.register(actor=scenario["user"], user=scenario["user"], data=data)
    with pytest.raises(ValidationError, match="ya están registrados"):
        SubjectService.register(actor=scenario["user"], user=scenario["user"], data=data)
    assert ClassSchedule.objects.filter(subject=subject).count() == 3


def test_invalid_subject_interval_and_weeks_rejected(scenario):
    for data in (subject_data(end_time=time(9)), subject_data(weeks=100)):
        with pytest.raises(ValidationError):
            SubjectService.register(actor=scenario["user"], user=scenario["user"], data=data)
    assert not Subject.objects.exists()


def test_admin_can_register_subject_for_another_user(client, manager, scenario):
    client.force_login(manager)
    data = subject_data()
    response = client.post(reverse("manage_subjects", args=[scenario["user"].pk]), data)
    assert response.status_code == 302
    subject = Subject.objects.get()
    assert subject.registered_by == manager


def test_subject_retirement_preserves_history_and_blocks_further_booking(scenario):
    subject = SubjectService.register(
        actor=scenario["user"], user=scenario["user"], data=subject_data()
    )
    first = ClassSchedule.objects.filter(subject=subject).first()
    SubjectService.retire(actor=scenario["user"], subject_id=subject.pk)
    assert ClassSchedule.objects.filter(subject=subject).count() == 3
    assert not ClassSchedule.objects.filter(subject=subject, active=True).exists()
    with pytest.raises(ValidationError, match="horarios"):
        ReservationService.reserve(
            user=scenario["user"],
            vehicle=scenario["vehicle"],
            parking_lot=scenario["parking_lot"],
            starts_at=first.starts_at,
            ends_at=first.ends_at,
        )


def test_subject_with_pending_booking_cannot_be_retired(scenario):
    subject = SubjectService.register(
        actor=scenario["user"], user=scenario["user"], data=subject_data()
    )
    first = ClassSchedule.objects.filter(subject=subject).first()
    ReservationService.reserve(
        user=scenario["user"],
        vehicle=scenario["vehicle"],
        parking_lot=scenario["parking_lot"],
        starts_at=first.starts_at,
        ends_at=first.ends_at,
    )
    with pytest.raises(ValidationError, match="reservas pendientes"):
        SubjectService.retire(actor=scenario["user"], subject_id=subject.pk)


def test_student_cannot_manage_another_students_subjects(client, scenario):
    subject = SubjectService.register(
        actor=scenario["user"], user=scenario["user"], data=subject_data()
    )
    client.force_login(scenario["officer"])
    assert client.get(reverse("manage_subjects", args=[scenario["user"].pk])).status_code == 403
    assert client.post(reverse("retire_subject", args=[subject.pk])).status_code == 403


def test_create_and_deactivate_empty_lot(manager, client):
    client.force_login(manager)
    response = client.post(
        reverse("manage_lot_create"), {"name": "Nuevo", "capacity": 20, "active": "on"}
    )
    assert response.status_code == 302
    lot = ParkingLot.objects.get(name="Nuevo")
    response = client.post(
        reverse("manage_lot_edit", args=[lot.pk]), {"name": "Nuevo", "capacity": 20}
    )
    assert response.status_code == 302
    lot.refresh_from_db()
    assert not lot.active


def test_capacity_cannot_drop_below_committed_reservations(manager, scenario):
    scenario["parking_lot"].capacity = 2
    scenario["parking_lot"].save()
    reserve(scenario)
    reserve(scenario, plate="XYZ789")
    with pytest.raises(ValidationError, match="capacidad"):
        AdministrationService.save_lot(
            actor=manager,
            lot_id=scenario["parking_lot"].pk,
            data={"name": "Norte", "capacity": 1, "active": True},
        )


def test_busy_lot_cannot_be_deactivated(manager, scenario):
    reserve(scenario)
    with pytest.raises(ValidationError, match="desactivar"):
        AdministrationService.save_lot(
            actor=manager,
            lot_id=scenario["parking_lot"].pk,
            data={"name": "Norte", "capacity": 1, "active": False},
        )


def test_inactive_lot_hidden_and_unbookable(client, scenario):
    scenario["parking_lot"].active = False
    scenario["parking_lot"].save()
    client.force_login(scenario["user"])
    assert client.get(reverse("availability")).json()["lots"] == []
    with pytest.raises(ValidationError, match="disponible"):
        reserve(scenario)


def test_automatic_assignment_uses_lot_with_most_free_spaces(scenario):
    best = ParkingLot.objects.create(name="Mayor cupo", capacity=5)
    reservation = reserve(scenario, parking_lot=None)
    assert reservation.parking_lot == best


def test_recommendation_endpoint_and_tampered_dates(client, scenario):
    best = ParkingLot.objects.create(name="Mayor cupo", capacity=5)
    client.force_login(scenario["user"])
    params = {
        "starts_at": timezone.localtime(scenario["starts_at"]).strftime("%Y-%m-%dT%H:%M"),
        "ends_at": timezone.localtime(scenario["ends_at"]).strftime("%Y-%m-%dT%H:%M"),
    }
    response = client.get(reverse("recommendation"), params)
    assert response.status_code == 200 and response.json()["recommended"]["id"] == best.pk
    assert client.get(reverse("recommendation"), params | {"ends_at": "invalid"}).status_code == 400
    assert (
        client.get(reverse("recommendation"), params | {"ends_at": "2099-01-01T10:00"}).status_code
        == 400
    )


def test_recommendation_counts_adjacent_intervals_correctly(scenario):
    lot = scenario["parking_lot"]
    lot.capacity = 2
    lot.save()
    middle = scenario["starts_at"] + timedelta(hours=1)
    reserve(scenario, ends_at=middle)
    reserve(scenario, starts_at=middle, plate="XYZ789")
    options = interval_recommendations(scenario["starts_at"], scenario["ends_at"])
    assert options[0]["free"] == 1


def test_automatic_assignment_rejects_when_every_lot_is_full(scenario):
    reserve(scenario)
    with pytest.raises(ValidationError, match="espacios"):
        reserve(scenario, parking_lot=None, plate="XYZ789")


def test_alerts_respect_window_state_and_assignment(client, scenario):
    now = timezone.now().replace(second=0, microsecond=0)

    def row(plate, minutes, lot=None, status="confirmed"):
        start = now + timedelta(minutes=minutes)
        return Reservation.objects.create(
            user=scenario["user"],
            parking_lot=lot or scenario["parking_lot"],
            plate=plate,
            starts_at=start,
            ends_at=start + timedelta(hours=2),
            entry_deadline=start + timedelta(minutes=15),
            status=status,
        )

    row("SOON", 30)
    row("LATER", 31)
    row("PENDING", -5)
    row("EXPIRED", -20)
    row("CANCELLED", 10, status="cancelled")
    row("OTHER", 5, lot=ParkingLot.objects.create(name="Otro", capacity=5))
    client.force_login(scenario["officer"])
    with patch("parking.queries.timezone.now", return_value=now):
        data = client.get(reverse("alerts_data")).json()
    assert data["upcoming_count"] == 1 and data["pending_count"] == 1
    assert [item["plate"] for item in data["upcoming"]] == ["SOON"]
    assert [item["plate"] for item in data["pending"]] == ["PENDING"]


def test_alerts_are_not_visible_to_students(client, scenario):
    client.force_login(scenario["user"])
    assert client.get(reverse("alerts_data")).status_code == 302


def test_monthly_metrics_use_costa_rica_month_boundary(scenario):
    start = timezone.make_aware(datetime(2026, 11, 30, 23, 45))
    Reservation.objects.create(
        user=scenario["user"],
        parking_lot=scenario["parking_lot"],
        plate="MIDNIGHT",
        starts_at=start,
        ends_at=start + timedelta(hours=1),
        status="cancelled",
    )
    result = monthly_summary(date(2026, 11, 1))
    assert result["total"] == 1 and result["cancelled"] == 1
    assert result["peak_hour"] == "23:00"
    assert monthly_summary(date(2026, 12, 1))["total"] == 0


def test_monthly_indicators_permissions_and_empty_results(client, manager, scenario):
    client.force_login(scenario["user"])
    assert client.get(reverse("indicators")).status_code == 403
    client.force_login(manager)
    response = client.get(reverse("indicators"), {"month": "2020-01"})
    assert response.status_code == 200
    assert response.context["summary"]["total"] == 0
    invalid = client.get(reverse("indicators"), {"month": "2026-13"})
    assert invalid.status_code == 200 and invalid.context["summary"] is None


def test_countdown_has_machine_readable_timestamps(client, scenario):
    reserve(scenario)
    client.force_login(scenario["user"])
    content = client.get(reverse("dashboard")).content.decode()
    assert 'id="arrival-countdown"' in content
    assert 'data-start="' in content and 'data-deadline="' in content
