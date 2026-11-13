import json
from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from parking.models import AuditEvent, OfflineMovement, ParkingLot, Reservation
from parking.services import ReservationService


def manager():
    return get_user_model().objects.create_user("manager", is_superuser=True, is_staff=True)


def visitor(scenario, **kwargs):
    data = {key: scenario[key] for key in ("parking_lot", "starts_at", "ends_at")}
    data.update(
        user=kwargs.get("user") or manager(),
        vehicle=None,
        guest_name="Ana Solano",
        guest_plate="VIS123",
    )
    data.update(kwargs)
    return ReservationService.reserve(**data)


def active_reservation(scenario):
    now = timezone.now()
    return Reservation.objects.create(
        user=scenario["user"],
        parking_lot=scenario["parking_lot"],
        plate="ABC123",
        starts_at=now - timedelta(minutes=5),
        ends_at=now + timedelta(hours=1),
        entry_deadline=now + timedelta(minutes=10),
    )


def event(row, **kwargs):
    data = {
        "id": str(uuid4()),
        "code": str(row.code),
        "action": "entry",
        "occurred_at": timezone.now().isoformat(),
    }
    data.update(kwargs)
    return data


def send(client, payload):
    return client.post(
        reverse("sync_movement"), json.dumps(payload), content_type="application/json"
    )


def test_visitor_reuses_capacity_and_code(scenario):
    row = visitor(scenario)
    assert row.kind == Reservation.Kind.VISITOR and row.vehicle is None
    assert row.plate == "VIS123" and row.code and row.guest_name == "Ana Solano"
    with pytest.raises(ValidationError, match="espacios"):
        visitor(scenario, user=row.user, guest_plate="VIS456")


def test_visitor_requires_administrator(scenario, client):
    with pytest.raises(ValidationError, match="administración"):
        visitor(scenario, user=scenario["officer"])
    client.force_login(scenario["user"])
    assert client.get(reverse("visitor_create")).status_code == 403
    client.force_login(scenario["officer"])
    assert client.get(reverse("visitor_create")).status_code == 403


def test_visitor_http_confirmation_and_security_qr(scenario, client):
    admin = manager()
    client.force_login(admin)
    response = client.post(
        reverse("visitor_create"),
        {
            "guest_name": "Ana",
            "guest_plate": "vis123",
            "parking_lot": scenario["parking_lot"].pk,
            "starts_at": timezone.localtime(scenario["starts_at"]).strftime("%Y-%m-%dT%H:%M"),
            "ends_at": timezone.localtime(scenario["ends_at"]).strftime("%Y-%m-%dT%H:%M"),
        },
    )
    assert response.status_code == 302
    row = Reservation.objects.get(kind="visitor")
    assert str(row.code) in response.url
    client.force_login(scenario["officer"])
    assert client.get(response.url).status_code == 200
    assert client.get(reverse("reservation_qr", args=[row.code])).status_code == 200


def test_exception_audited_and_reported(scenario, client):
    row = ReservationService.admit_exception(
        officer=scenario["officer"],
        parking_lot=scenario["parking_lot"],
        plate="exc123",
        reason="Atención urgente",
        ends_at=timezone.now() + timedelta(hours=1),
    )
    assert row.status == "inside" and row.entered_at and row.officer == scenario["officer"]
    assert row.kind == "exception" and row.exception_reason == "Atención urgente"
    assert AuditEvent.objects.filter(reservation=row, action="entered").count() == 1
    client.force_login(manager())
    assert (
        "Ingreso excepcional"
        in client.get(reverse("reports"), {"kind": "exception"}).content.decode()
    )
    assert "Atención urgente" in client.get(
        reverse("report_csv"), {"kind": "exception"}
    ).content.decode("utf-8-sig")
    from io import BytesIO

    from openpyxl import load_workbook

    workbook = load_workbook(BytesIO(client.get(reverse("report_excel")).content))
    assert workbook.active["M6"].value == "Ingreso excepcional"
    assert workbook.active["O6"].value == "Atención urgente"
    ReservationService.check_out(reservation_id=row.pk, officer=scenario["officer"])


@pytest.mark.parametrize("reason", ["", "x" * 251])
def test_exception_requires_reason(scenario, reason):
    with pytest.raises(ValidationError):
        ReservationService.admit_exception(
            officer=scenario["officer"],
            parking_lot=scenario["parking_lot"],
            plate="EXC123",
            reason=reason,
            ends_at=timezone.now() + timedelta(hours=1),
        )
    assert not Reservation.objects.exists()


def test_exception_assignment_and_capacity(scenario):
    other = ParkingLot.objects.create(name="Sur", capacity=2)
    with pytest.raises(ValidationError, match="asignado"):
        ReservationService.admit_exception(
            officer=scenario["officer"],
            parking_lot=other,
            plate="EXC123",
            reason="Visita",
            ends_at=timezone.now() + timedelta(hours=1),
        )
    row = active_reservation(scenario)
    ReservationService.check_in(reservation_id=row.pk, officer=scenario["officer"])
    with pytest.raises(ValidationError, match="cupo"):
        ReservationService.admit_exception(
            officer=scenario["officer"],
            parking_lot=scenario["parking_lot"],
            plate="EXC123",
            reason="Visita",
            ends_at=timezone.now() + timedelta(hours=1),
        )


def test_offline_entry_exit_and_idempotent_retry(scenario, client):
    row = active_reservation(scenario)
    client.force_login(scenario["officer"])
    payload = event(row)
    assert send(client, payload).json()["accepted"]
    assert send(client, payload).json()["accepted"]
    row.refresh_from_db()
    assert row.entered_at.isoformat() == payload["occurred_at"]
    exit_payload = event(row, action="exit")
    assert send(client, exit_payload).json()["accepted"]
    assert send(client, exit_payload).json()["accepted"]
    assert OfflineMovement.objects.count() == 2
    assert AuditEvent.objects.filter(reservation=row, action="entered").count() == 1
    assert AuditEvent.objects.filter(reservation=row, action="exited").count() == 1


def test_offline_conflict_persisted_and_not_retried(scenario, client):
    row = active_reservation(scenario)
    client.force_login(scenario["officer"])
    payload = event(row, occurred_at=(row.starts_at - timedelta(minutes=1)).isoformat())
    first = send(client, payload).json()
    assert not first["accepted"] and first["error"]
    assert send(client, payload).json() == first
    row.refresh_from_db()
    assert row.status == "confirmed" and OfflineMovement.objects.count() == 1
    assert not AuditEvent.objects.filter(reservation=row, action="entered").exists()


def test_offline_uuid_cannot_change_payload(scenario, client):
    row = active_reservation(scenario)
    client.force_login(scenario["officer"])
    payload = event(row)
    assert send(client, payload).json()["accepted"]
    assert send(client, {**payload, "action": "exit"}).status_code == 409


@pytest.mark.parametrize("offset", [timedelta(days=-2), timedelta(minutes=5)])
def test_offline_clock_limits(scenario, client, offset):
    row = active_reservation(scenario)
    client.force_login(scenario["officer"])
    assert not send(client, event(row, occurred_at=(timezone.now() + offset).isoformat())).json()[
        "accepted"
    ]


def test_offline_delayed_sync_after_expiry(scenario, client):
    row = active_reservation(scenario)
    captured = timezone.now() - timedelta(minutes=2)
    row.entry_deadline = timezone.now() - timedelta(minutes=1)
    row.status = Reservation.Status.EXPIRED
    row.save()
    client.force_login(scenario["officer"])
    assert send(client, event(row, occurred_at=captured.isoformat())).json()["accepted"]
    row.refresh_from_db()
    assert row.status == "inside"


def test_offline_scope_and_auth(scenario, client):
    row = active_reservation(scenario)
    assert send(client, event(row)).status_code == 403
    client.force_login(scenario["user"])
    assert send(client, event(row)).status_code == 403
    assert client.get(reverse("offline_context")).status_code == 403
    client.force_login(scenario["officer"])
    context = client.get(reverse("offline_context"))
    assert context.json()["rows"][0]["code"] == str(row.code)
    assert "no-store" in context["Cache-Control"]
    scenario["officer"].securityassignment_set.all().delete()
    assert send(client, event(row)).status_code == 404


def test_offline_csrf_and_public_shell(scenario, client):
    from django.test import Client

    secure = Client(enforce_csrf_checks=True)
    secure.force_login(scenario["officer"])
    assert send(secure, event(active_reservation(scenario))).status_code == 403
    assert client.get(reverse("offline_shell")).status_code == 200
    worker = client.get(reverse("service_worker"))
    assert worker["Content-Type"] == "application/javascript"
    assert b"/acceso/dispositivo/" in worker.content
    assert b"/acceso/contexto/" not in worker.content
