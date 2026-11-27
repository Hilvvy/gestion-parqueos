from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from parking.administration import AdministrationService
from parking.forms import PolicyForm
from parking.models import AuditEvent, OfflineMovement, ParkingPolicy, Reservation
from parking.services import ReservationService
from parking.tests.test_visitors_offline import active_reservation, event, manager, send


@pytest.mark.parametrize(
    "offset,window,cancellable",
    [(10, False, True), (0, True, False), (-5, True, False), (-20, False, False)],
)
def test_actions_follow_the_same_window_as_the_service(
    scenario, client, offset, window, cancellable
):
    now = timezone.now()
    row = Reservation.objects.create(
        user=scenario["user"],
        parking_lot=scenario["parking_lot"],
        plate="WIN123",
        starts_at=now + timedelta(minutes=offset),
        ends_at=now + timedelta(hours=1),
        entry_deadline=now + timedelta(minutes=offset + 15),
    )
    with patch("parking.models.timezone.now", return_value=now):
        assert row.entry_window_open is window and row.can_cancel is cancellable
        client.force_login(scenario["user"])
        cancel_url = reverse("cancel", args=[row.pk])
        for url in [reverse("dashboard"), reverse("reservation_detail", args=[row.code])]:
            assert (f'action="{cancel_url}"' in client.get(url).content.decode()) is cancellable
        client.force_login(scenario["officer"])
        content = client.get(reverse("access")).content.decode()
        assert (f'action="{reverse("movement", args=[row.pk, "entry"])}"' in content) is window


def test_next_reservation_skips_unprocessed_no_show(scenario, client):
    stale = active_reservation(scenario)
    stale.entry_deadline = timezone.now() - timedelta(seconds=1)
    stale.save()
    upcoming = Reservation.objects.create(
        user=scenario["user"],
        parking_lot=scenario["parking_lot"],
        plate="NEXT123",
        starts_at=scenario["starts_at"],
        ends_at=scenario["ends_at"],
        entry_deadline=scenario["starts_at"] + timedelta(minutes=15),
    )
    client.force_login(scenario["user"])
    assert client.get(reverse("dashboard")).context["next_reservation"] == upcoming


def test_exception_releases_no_show_without_waiting_for_worker(scenario):
    stale = active_reservation(scenario)
    stale.entry_deadline = timezone.now() - timedelta(seconds=1)
    stale.save()
    row = ReservationService.admit_exception(
        officer=scenario["officer"],
        parking_lot=scenario["parking_lot"],
        plate="EXC123",
        reason="Visita autorizada",
        ends_at=timezone.now() + timedelta(minutes=30),
    )
    assert row.status == "inside"
    stale.refresh_from_db()
    assert stale.status == "expired"
    assert AuditEvent.objects.filter(reservation=stale, action="expired").count() == 1


def test_queue_cannot_be_synced_under_a_different_account(scenario, client):
    row = active_reservation(scenario)
    payload = event(row, user=scenario["officer"].pk)
    client.force_login(manager())
    response = send(client, payload)
    assert response.status_code == 403 and "otra cuenta" in response.json()["error"]
    assert not OfflineMovement.objects.exists()
    row.refresh_from_db()
    assert row.status == "confirmed"


@pytest.mark.parametrize("payload", [[], {}, {"user": float("inf")}, {"user": "invalid"}])
def test_malformed_offline_record_is_a_client_error(scenario, client, payload):
    import json

    client.force_login(scenario["officer"])
    response = client.post(
        reverse("sync_movement"), json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 400
    assert not OfflineMovement.objects.exists()


def test_zero_tolerance_does_not_make_arrival_impossible(db):
    policy = ParkingPolicy.objects.create(arrival_tolerance_minutes=15)
    assert not PolicyForm({"arrival_tolerance_minutes": 0}, instance=policy).is_valid()
    with pytest.raises(ValidationError):
        AdministrationService.save_policy(actor=manager(), minutes=0)
    policy.refresh_from_db()
    assert policy.arrival_tolerance_minutes == 15
