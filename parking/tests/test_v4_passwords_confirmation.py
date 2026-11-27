from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from parking.models import AuditEvent, Reservation, UserProfile
from parking.passwords import PasswordService
from parking.permissions import configure_roles
from parking.validators import reservation_code

OLD = "OriginalSecure2026!"
TEMPORARY = "TemporalSecure2026!"
NEW = "ReplacedSecure2026!"


@pytest.fixture
def accounts(db):
    User = get_user_model()
    admin = User.objects.create_user("manager-v4", email="manager@ulacit.ed.cr", password=OLD)
    student = User.objects.create_user("student-v4", email="student@ulacit.ed.cr", password=OLD)
    officer = User.objects.create_user("officer-v4", email="officer@ulacit.ed.cr", password=OLD)
    security_group, admin_group = configure_roles()
    admin.groups.add(admin_group)
    officer.groups.add(security_group)
    return admin, student, officer


def login(user):
    client = Client()
    assert client.login(username=user.email, password=OLD)
    return client


def test_reset_invalidates_existing_sessions_and_forces_change(accounts):
    admin, student, _ = accounts
    first, second = login(student), login(student)
    PasswordService.reset(actor=admin, user_id=student.pk, temporary_password=TEMPORARY)
    student.refresh_from_db()
    assert student.check_password(TEMPORARY) and student.userprofile.must_change_password
    for client in (first, second):
        assert client.get(reverse("dashboard")).url.startswith(reverse("login"))
        assert not client.login(username=student.email, password=OLD)
    assert first.login(username=student.email, password=TEMPORARY)
    assert first.get(reverse("dashboard")).url == reverse("password_change")
    assert first.get(reverse("reserve")).url == reverse("password_change")
    assert first.get("/admin/").url == reverse("password_change")
    response = first.post(
        reverse("password_change"),
        {"old_password": TEMPORARY, "new_password1": NEW, "new_password2": NEW},
    )
    assert response.status_code == 302 and response.url == reverse("dashboard")
    assert first.get(reverse("dashboard")).status_code == 200
    student.refresh_from_db()
    assert student.check_password(NEW) and not student.userprofile.must_change_password
    assert (
        AuditEvent.objects.filter(
            subject_user=student, action="password_reset", actor=admin
        ).count()
        == 1
    )
    assert (
        AuditEvent.objects.filter(
            subject_user=student, action="password_changed", actor=student
        ).count()
        == 1
    )


def test_change_password_keeps_current_session_and_revokes_others(accounts):
    _, student, _ = accounts
    current, other = login(student), login(student)
    response = current.post(
        reverse("password_change"),
        {"old_password": OLD, "new_password1": NEW, "new_password2": NEW},
    )
    assert response.status_code == 302
    assert current.get(reverse("profile")).status_code == 200
    assert other.get(reverse("profile")).url.startswith(reverse("login"))


@pytest.mark.parametrize("role", [1, 2])
def test_admin_can_reset_student_and_security(accounts, role):
    admin, *others = accounts
    target = accounts[role]
    response = login(admin).post(
        reverse("manage_password_reset", args=[target.pk]),
        {"new_password1": TEMPORARY, "new_password2": TEMPORARY},
    )
    assert response.status_code == 302
    target.refresh_from_db()
    assert target.check_password(TEMPORARY)
    assert target.userprofile.must_change_password


def test_reset_requires_admin_and_does_not_allow_admin_targets(accounts):
    admin, student, officer = accounts
    for actor in (student, officer):
        with pytest.raises(PermissionDenied):
            PasswordService.reset(actor=actor, user_id=student.pk, temporary_password=TEMPORARY)
        assert (
            login(actor).get(reverse("manage_password_reset", args=[student.pk])).status_code == 403
        )
    with pytest.raises(PermissionDenied):
        PasswordService.reset(actor=admin, user_id=admin.pk, temporary_password=TEMPORARY)
    assert (
        login(admin)
        .post(
            reverse("manage_password_reset", args=[admin.pk]),
            {"new_password1": TEMPORARY, "new_password2": TEMPORARY},
        )
        .status_code
        == 403
    )
    assert not AuditEvent.objects.filter(action="password_reset").exists()


@pytest.mark.parametrize("password", ["short", "1234567890", OLD])
def test_reset_rejects_weak_and_current_password(accounts, password):
    admin, student, _ = accounts
    with pytest.raises(ValidationError):
        PasswordService.reset(actor=admin, user_id=student.pk, temporary_password=password)
    student.refresh_from_db()
    assert student.check_password(OLD)
    assert not AuditEvent.objects.filter(action="password_reset").exists()


def test_password_change_requires_current_matching_and_different_password(accounts):
    _, student, _ = accounts
    client = login(student)
    for old, new, confirm in [("incorrect", NEW, NEW), (OLD, NEW, TEMPORARY), (OLD, OLD, OLD)]:
        response = client.post(
            reverse("password_change"),
            {"old_password": old, "new_password1": new, "new_password2": confirm},
        )
        assert response.status_code == 200 and response.context["form"].errors
        assert NEW not in response.content.decode() and TEMPORARY not in response.content.decode()
    student.refresh_from_db()
    assert student.check_password(OLD)


def test_forced_change_blocks_api_and_post_but_allows_logout(accounts):
    admin, student, _ = accounts
    PasswordService.reset(actor=admin, user_id=student.pk, temporary_password=TEMPORARY)
    client = Client()
    assert client.login(username=student.email, password=TEMPORARY)
    response = client.post(reverse("sync_movement"), {}, content_type="application/json")
    assert response.status_code == 403 and response.json()["password_change_url"] == reverse(
        "password_change"
    )
    assert client.post(reverse("vehicles"), {}).url == reverse("password_change")
    page = client.get(reverse("password_change")).content.decode()
    assert 'id="app-sidebar"' not in page and 'class="with-sidebar"' not in page
    assert client.post(reverse("logout")).status_code == 302
    assert client.get(reverse("password_change")).url.startswith(reverse("login"))


def test_password_reset_is_post_only_for_mutation_and_csrf_protected(accounts):
    admin, student, _ = accounts
    client = login(admin)
    response = client.get(reverse("manage_password_reset", args=[student.pk]))
    assert response.status_code == 200 and "no-store" in response["Cache-Control"]
    assert not AuditEvent.objects.filter(action="password_reset").exists()
    secure = Client(enforce_csrf_checks=True)
    secure.force_login(admin)
    assert (
        secure.post(
            reverse("manage_password_reset", args=[student.pk]),
            {"new_password1": TEMPORARY, "new_password2": TEMPORARY},
        ).status_code
        == 403
    )


def test_service_rechecks_old_password_after_concurrent_reset(accounts):
    admin, student, _ = accounts
    PasswordService.reset(actor=admin, user_id=student.pk, temporary_password=TEMPORARY)
    with pytest.raises(ValidationError, match="actual"):
        PasswordService.change(actor=student, old_password=OLD, new_password=NEW)


def test_password_change_audit_failure_rolls_back_password(accounts):
    admin, student, _ = accounts
    with patch(
        "parking.passwords.AuditEvent.objects.create", side_effect=RuntimeError("audit failure")
    ):
        with pytest.raises(RuntimeError):
            PasswordService.reset(actor=admin, user_id=student.pk, temporary_password=TEMPORARY)
    student.refresh_from_db()
    assert student.check_password(OLD)
    assert not UserProfile.objects.filter(user=student, must_change_password=True).exists()


def confirmation_reservation(scenario, **kwargs):
    now = timezone.now()
    data = dict(
        user=scenario["user"],
        parking_lot=scenario["parking_lot"],
        plate="SECRET123",
        starts_at=now - timedelta(minutes=1),
        ends_at=now + timedelta(hours=1),
        entry_deadline=now + timedelta(minutes=14),
    )
    data.update(kwargs)
    return Reservation.objects.create(**data)


def test_public_confirmation_contains_only_allowed_data(scenario, client):
    user = scenario["user"]
    user.first_name, user.last_name, user.email = (
        "PRIVATE_NAME",
        "PRIVATE_SURNAME",
        "private@ulacit.ed.cr",
    )
    user.save()
    UserProfile.objects.create(user=user, national_id="PRIVATE_ID")
    row = confirmation_reservation(
        scenario, guest_name="PRIVATE_GUEST", exception_reason="PRIVATE_REASON"
    )
    response = client.get(reverse("public_confirmation", args=[row.code]))
    body = response.content.decode()
    assert response.status_code == 200 and "***123" in body and "Confirmada" in body
    assert str(row.code) in body
    for secret in [
        user.first_name,
        user.last_name,
        user.email,
        "PRIVATE_ID",
        row.plate,
        row.guest_name,
        row.exception_reason,
        user.username,
    ]:
        assert secret not in body
    assert "reservation" not in response.context
    assert "no-store" in response["Cache-Control"]
    assert response["Referrer-Policy"] == "no-referrer"
    assert "noindex" in response["X-Robots-Tag"]
    assert 'id="app-sidebar"' not in body
    client.force_login(scenario["officer"])
    assert (
        'id="app-sidebar"'
        not in client.get(reverse("public_confirmation", args=[row.code])).content.decode()
    )


@pytest.mark.parametrize(
    "status,label",
    [
        ("cancelled", "Cancelada"),
        ("completed", "Finalizada"),
        ("inside", "En parqueo"),
        ("expired", "Vencida"),
    ],
)
def test_public_confirmation_shows_terminal_and_inside_states(scenario, client, status, label):
    row = confirmation_reservation(scenario, status=status)
    response = client.get(reverse("public_confirmation", args=[row.code]))
    assert label in response.content.decode()
    assert "Límite de ingreso" not in response.content.decode()


def test_public_confirmation_detects_expiry_without_mutating_on_get(scenario, client):
    row = confirmation_reservation(scenario, entry_deadline=timezone.now() - timedelta(seconds=1))
    response = client.get(reverse("public_confirmation", args=[row.code]))
    assert "Vencida" in response.content.decode()
    row.refresh_from_db()
    assert row.status == "confirmed" and not AuditEvent.objects.filter(reservation=row).exists()


def test_public_confirmation_unknown_code_and_read_only(scenario, client):
    row = confirmation_reservation(scenario)
    assert client.get(reverse("public_confirmation", args=[uuid4()])).status_code == 404
    assert client.post(reverse("public_confirmation", args=[row.code])).status_code == 405
    assert client.get(reverse("reservation_detail", args=[row.code])).status_code == 302
    assert client.get(reverse("reservation_qr", args=[row.code])).status_code == 302


def test_local_qr_embeds_public_url_and_old_code_search_still_works(scenario, client):
    row = confirmation_reservation(scenario)
    client.force_login(scenario["officer"])
    path = reverse("public_confirmation", args=[row.code])
    with patch("parking.views.segno.make") as make:
        response = client.get(reverse("reservation_qr", args=[row.code]))
        assert response.status_code == 200
        make.assert_called_once_with("http://testserver" + path, micro=False)
    for query in [str(row.code), "http://testserver" + path]:
        response = client.get(reverse("access"), {"search": query})
        assert row in response.context["reservations"]
    client.force_login(scenario["user"])
    assert client.post(reverse("movement", args=[row.pk, "entry"])).status_code == 302
    row.refresh_from_db()
    assert row.status == "confirmed"


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(1)",
        "https://example.com/other/123/",
        "/confirmacion/not-a-code/",
        "not-a-uuid",
    ],
)
def test_confirmation_parser_rejects_invalid_codes(value):
    with pytest.raises(ValueError):
        reservation_code(value)
